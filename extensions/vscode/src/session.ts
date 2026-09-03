/**
 * One window's worth of gandalf: the components, the state they share, and what
 * happens when a scan runs.
 *
 * Everything here used to be a closure inside `activate`, which meant the
 * lifecycle, the scan loop and every command body were one function sharing one
 * scope. The state is small — the last error, whether the "not found" notice has
 * been shown, and the label of the scan in flight — and it belongs with the
 * components that read it.
 */
import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

import { Coalescer } from './coalescer';
import { readSettings, Settings } from './config';
import { DiagnosticGroup, DiagnosticPublisher } from './diagnostics';
import { FailureNotifier } from './failures';
import { FindingsView } from './findingsView';
import { log } from './log';
import { gatesByDuration, gatesByStatus, normalize, normalizeGate, pathCache, slim } from './parse';
import { describeProgress, ScanProgress } from './progress';
import { ReportView } from './report';
import { probe, runGandalf, ScanKind } from './runner';
import { ContentGuard, Job, jobLabel, Scheduler } from './scheduler';
import { StatusBar } from './status';
import { excludesFor, outDirFor, pruneReports, scannable } from './storage';
import { ResultStore } from './store';
import { Snapshot } from './types';

/** Slowest gates named in the log when a project scan finishes. */
const TIMINGS_LOGGED = 5;
/** Let the window settle before forking ~30 gates. */
const STARTUP_DELAY_MS = 5000;

export class Session {
  readonly store = new ResultStore();
  readonly findingsView: FindingsView;
  readonly reportView = new ReportView();
  readonly scheduler: Scheduler;
  private readonly diagnostics = new DiagnosticPublisher();
  private readonly statusBar = new StatusBar();
  private readonly guard = new ContentGuard();
  private readonly failures = new FailureNotifier();

  /** Label of the scan in flight, if any — the status bar belongs to it. */
  private scanning: string | undefined;

  constructor(private readonly context: vscode.ExtensionContext) {
    this.findingsView = new FindingsView(this.store);
    this.scheduler = new Scheduler(
      (job, token) => this.execute(job, token),
      () => {
        const s = this.settingsFor(this.primaryFolder());
        return { debounceMs: s.debounceMs, intervalMinutes: s.intervalMinutes };
      },
    );
  }

  /** What the extension host must dispose, in the order it was created. */
  disposables(): vscode.Disposable[] {
    return [
      this.findingsView.register(),
      this.findingsView,
      this.store.onDidChange(() => this.paint()),
      this.store,
      this.diagnostics,
      this.statusBar,
      this.scheduler,
      { dispose: () => this.reportView.dispose() },
    ];
  }

  // --- the workspace ---------------------------------------------------------

  settingsFor(folder?: vscode.WorkspaceFolder): Settings {
    return readSettings(folder?.uri);
  }

  primaryFolder(): vscode.WorkspaceFolder | undefined {
    const active = vscode.window.activeTextEditor?.document.uri;
    return (
      (active ? vscode.workspace.getWorkspaceFolder(active) : undefined) ??
      vscode.workspace.workspaceFolders?.[0]
    );
  }

  paint(): void {
    const folder = this.primaryFolder();
    this.findingsView.refresh();
    // While a scan runs the status bar shows its progress; don't overwrite it
    // with an idle verdict just because a partial result landed.
    if (this.scanning !== undefined) return;
    this.statusBar.idle(
      folder ? this.store.lastRun(folder) : undefined,
      folder ? this.store.findings(folder).length : 0,
    );
  }

  /** Republish every folder's diagnostics — the collection is global. */
  publishDiagnostics(): void {
    const groups: DiagnosticGroup[] = this.store
      .folders()
      .map((f) => ({ findings: this.store.findings(f), settings: this.settingsFor(f) }));
    this.diagnostics.publish(groups);
  }

  // --- running a scan --------------------------------------------------------

  /** Where the result of one run belongs: the board, or a report on its own. */
  private keep(job: Job, snapshot: Snapshot, htmlPath: string, durationMs: number): void {
    if (job.kind === 'commit') {
      // A different scope entirely: it produces a report, not a new board.
      if (htmlPath) this.reportView.current = htmlPath;
    } else if (job.kind === 'file' && job.absPath) {
      this.store.setFile(job.folder, job.absPath, snapshot, durationMs);
    } else {
      this.store.setProject(job.folder, snapshot, durationMs);
      if (htmlPath) this.reportView.current = htmlPath;
    }
  }

  /**
   * Where the time went. Gandalf records each gate's wall-clock in the payload,
   * so a slow scan can name its own culprits instead of leaving the user to
   * guess which of ~30 gates to disable.
   */
  private logTimings(payload: Snapshot['payload'], totalMs: number): void {
    const timed = gatesByDuration(payload);
    if (timed.length === 0) return;
    const top = timed
      .slice(0, TIMINGS_LOGGED)
      .map((g) => `${g.name} ${(g.duration ?? 0).toFixed(1)}s`)
      .join(', ');
    log().info(`slowest gates (of ${timed.length}) in ${(totalMs / 1000).toFixed(1)}s: ${top}`);
  }

  private async execute(job: Job, token: vscode.CancellationToken): Promise<void> {
    const s = this.settingsFor(job.folder);
    const isProjectScope = job.kind !== 'file';

    // Hashed once: the answer to "did this change" is also what gets committed
    // if the run succeeds.
    const scanned = job.absPath ? await this.guard.inspect(job.absPath) : undefined;
    if (job.kind === 'file' && !job.manual && scanned?.unchanged) {
      log().debug(`unchanged since last scan, skipping: ${job.relPath}`);
      return;
    }

    this.scanning = jobLabel(job);
    this.findingsView.setScanning(jobLabel(job));
    this.statusBar.scanning(jobLabel(job));
    // One cache for the whole run: streaming normalizes gate by gate, and a
    // fresh cache per gate re-stats paths earlier gates already resolved.
    const paths = pathCache();
    const coalescer = new Coalescer(() => this.findingsView.refresh());
    const onProgress = (p: ScanProgress) => {
      this.statusBar.scanning(jobLabel(job), p);
      this.findingsView.setScanning(`${jobLabel(job)} · ${describeProgress(p)}`);
      job.report?.(p);
    };
    try {
      const outDir = outDirFor(this.context, job.folder);
      const result = await runGandalf(
        {
          folder: job.folder,
          kind: job.kind,
          relPath: job.relPath,
          commit: job.commit,
          llm: job.llm ?? s.llm,
          html: isProjectScope, // A one-file scorecard is not the report anyone wants.
          outDir,
          excludes: excludesFor(job.folder, s),
          reason: job.reason,
          onProgress,
          onStart: () => this.store.beginStream(job.folder),
          onGate: (gate) => {
            this.store.pushStream(
              job.folder,
              gate.name,
              normalizeGate(gate, job.folder.uri.fsPath, paths),
            );
            coalescer.soon();
          },
        },
        s,
        token,
      );

      const { blocked, inapplicable } = gatesByStatus(result.payload);
      const snapshot: Snapshot = {
        findings: normalize(result.payload, job.folder.uri.fsPath, paths),
        blocked,
        inapplicable,
        // Slimmed last: everything above still needed the raw findings.
        payload: slim(result.payload),
        jsonPath: result.jsonPath,
        htmlPath: result.htmlPath,
        scope: result.payload.scope,
        at: Date.now(),
      };
      this.keep(job, snapshot, result.htmlPath, result.durationMs);
      // Only remembered on success — a failed scan must not suppress the retry.
      if (job.absPath && scanned) this.guard.commit(job.absPath, scanned.hash);
      this.publishDiagnostics();
      if (isProjectScope) this.logTimings(result.payload, result.durationMs);
      await pruneReports(outDir);
    } catch (err) {
      this.failures.report(err, job);
    } finally {
      coalescer.cancel();
      // The report (or the failure) is now the whole truth — drop the partials.
      this.store.endStream(job.folder);
      this.scanning = undefined;
      this.findingsView.setScanning('');
      this.paint();
    }
  }

  // --- what a command asks for -----------------------------------------------

  private manualJob(kind: ScanKind, extra: Partial<Job> = {}): Job | undefined {
    const doc = vscode.window.activeTextEditor?.document;
    const folder =
      kind === 'file'
        ? doc?.uri.scheme === 'file'
          ? vscode.workspace.getWorkspaceFolder(doc.uri)
          : undefined
        : this.primaryFolder();
    if (!folder) {
      void vscode.window.showWarningMessage(
        kind === 'file'
          ? 'Gandalf: open a file inside a workspace folder first.'
          : 'Gandalf: open a folder to scan.',
      );
      return undefined;
    }
    const job: Job = { folder, kind, reason: 'command', manual: true, ...extra };
    if (kind === 'file' && doc) {
      job.absPath = doc.uri.fsPath;
      job.relPath = path.relative(folder.uri.fsPath, doc.uri.fsPath);
    }
    return job;
  }

  /** Run a scan the user asked for. False when there was nothing to scan. */
  async run(kind: ScanKind, extra: Partial<Job> = {}): Promise<boolean> {
    const job = this.manualJob(kind, extra);
    if (!job) return false;
    // A whole-tree scan runs for minutes, so it gets a notification with a real
    // bar and a Cancel button. A one-file scan is seconds — the status bar is
    // enough, and a popup for it would be noise.
    const heavy = kind !== 'file';
    await vscode.window.withProgress(
      {
        location: heavy ? vscode.ProgressLocation.Notification : vscode.ProgressLocation.Window,
        title: `Gandalf: scanning ${jobLabel(job)}`,
        cancellable: heavy,
      },
      (progress, token) => {
        let reported = 0;
        job.report = (p: ScanProgress) => {
          progress.report({
            message: describeProgress(p),
            increment: Math.max(0, p.percent - reported),
          });
          reported = Math.max(reported, p.percent);
        };
        token.onCancellationRequested(() => this.scheduler.cancelJob(job));
        return this.scheduler.runNow(job);
      },
    );
    return true;
  }

  async openReport(llm: boolean): Promise<void> {
    const folder = this.primaryFolder();
    if (!folder) return;
    if (llm || !this.reportView.current || !fs.existsSync(this.reportView.current)) {
      const ok = await this.run('workspace', {
        llm: llm || undefined,
        reason: llm ? 'report + LLM summary' : 'report',
      });
      if (!ok) return;
    }
    if (!this.reportView.current) {
      void vscode.window.showWarningMessage(
        'Gandalf: no report available — the scan did not complete.',
      );
      return;
    }
    const snapshot = this.store.project(folder);
    await this.reportView.show(this.reportView.current, snapshot?.scope ?? folder.name);
  }

  // --- triggers --------------------------------------------------------------

  armSweep(): void {
    const s = this.settingsFor(this.primaryFolder());
    this.scheduler.setSweep(
      s.trigger === 'interval' || s.trigger === 'onSaveAndInterval',
      () => {
        const folder = this.primaryFolder();
        return folder
          ? { folder, kind: 'workspace' as ScanKind, reason: 'periodic sweep', manual: false }
          : undefined;
      },
    );
  }

  /** The extension's own configuration changed: re-read everything derived from it. */
  reconfigure(reset: () => void): void {
    reset();
    this.failures.reset();
    this.armSweep();
    this.publishDiagnostics();
    this.paint();
  }

  async onSave(doc: vscode.TextDocument): Promise<void> {
    if (doc.uri.scheme !== 'file') return;
    const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
    if (!folder) return;
    const s = this.settingsFor(folder);
    if (s.trigger !== 'onSave' && s.trigger !== 'onSaveAndInterval') return;

    const relPath = path.relative(folder.uri.fsPath, doc.uri.fsPath);
    if (!scannable(relPath)) return;
    // gandalf scans git-tracked files only — `--path` resolves through `git
    // ls-files` — so saving something git ignores (build output, a scratch
    // file) has nothing to scan, and scheduling a run just fails it.
    const tracked = await probe(
      'git',
      ['ls-files', '--error-unmatch', '--', relPath],
      folder.uri.fsPath,
    );
    if (!tracked.ok) return;

    this.scheduler.schedule({
      folder,
      kind: 'file',
      reason: `saved ${relPath}`,
      manual: false,
      relPath,
      absPath: doc.uri.fsPath,
    });
  }

  /** Arm the triggers, paint the chrome, and queue the startup scan. */
  start(): vscode.Disposable[] {
    this.armSweep();
    this.paint();
    log().info('Gandalf extension activated');

    const s = this.settingsFor(this.primaryFolder());
    if (!s.scanOnStartup || s.trigger === 'manual') return [];
    const timer = setTimeout(() => {
      const folder = this.primaryFolder();
      if (folder) {
        this.scheduler.schedule({ folder, kind: 'workspace', reason: 'startup', manual: false });
      }
    }, STARTUP_DELAY_MS);
    return [{ dispose: () => clearTimeout(timer) }];
  }
}
