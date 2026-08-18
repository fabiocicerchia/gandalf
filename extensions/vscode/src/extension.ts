import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import * as vscode from 'vscode';

import { readSettings, Settings } from './config';
import { DiagnosticGroup, DiagnosticPublisher } from './diagnostics';
import { enabledGlobs, excludePatterns } from './exclude';
import { Commit, delta, parseLog, parseTrend, sparkline, TrendEntry } from './history';
import { buildToolsImage, runDoctor } from './doctor';
import { FindingsView } from './findingsView';
import { disposeLog, log } from './log';
import { gatesByStatus, normalize, normalizeGate, pathCache, slim } from './parse';
import { describeProgress, ScanProgress } from './progress';
import { ReportView } from './report';
import {
  GandalfNotFoundError,
  probe,
  resetLauncherCache,
  runGandalf,
  ScanKind,
  ScanSkippedError,
} from './runner';
import { ContentGuard, Job, jobLabel, Scheduler } from './scheduler';
import { StatusBar } from './status';
import { ResultStore } from './store';
import { Snapshot } from './types';

const ERROR_COOLDOWN_MS = 60_000;
/** Reports the extension wrote and still keeps, oldest pruned beyond this. */
const REPORTS_KEPT = 8;

export function activate(context: vscode.ExtensionContext): void {
  const store = new ResultStore();
  const diagnostics = new DiagnosticPublisher();
  const statusBar = new StatusBar();
  const reportView = new ReportView();
  const findingsView = new FindingsView(store);
  const guard = new ContentGuard();

  let lastErrorAt = 0;
  let notFoundShown = false;
  /** Label of the scan in flight, if any — the status bar belongs to it. */
  let scanning: string | undefined;

  const settingsFor = (folder?: vscode.WorkspaceFolder): Settings => readSettings(folder?.uri);

  const primaryFolder = (): vscode.WorkspaceFolder | undefined => {
    const active = vscode.window.activeTextEditor?.document.uri;
    return (
      (active ? vscode.workspace.getWorkspaceFolder(active) : undefined) ??
      vscode.workspace.workspaceFolders?.[0]
    );
  };

  const paint = () => {
    const folder = primaryFolder();
    findingsView.refresh();
    // While a scan runs the status bar shows its progress; don't overwrite it
    // with an idle verdict just because a partial result landed.
    if (scanning !== undefined) return;
    statusBar.idle(
      folder ? store.lastRun(folder) : undefined,
      folder ? store.findings(folder).length : 0,
    );
  };

  /** Republish every folder's diagnostics — the collection is global. */
  const publishDiagnostics = () => {
    const groups: DiagnosticGroup[] = store
      .folders()
      .map((f) => ({ findings: store.findings(f), settings: settingsFor(f) }));
    diagnostics.publish(groups);
  };

  /**
   * What this folder should not scan: the extension's own setting, plus
   * whatever the editor already hides. Read per run rather than cached — these
   * are three config lookups, and a stale exclusion list would scan a tree the
   * user thought they had excluded.
   */
  const excludesFor = (folder: vscode.WorkspaceFolder, s: Settings): string[] => {
    if (!s.useEditorExcludes) return excludePatterns(s.exclude);
    const files = vscode.workspace.getConfiguration('files', folder.uri).get('exclude');
    const search = vscode.workspace.getConfiguration('search', folder.uri).get('exclude');
    return excludePatterns(s.exclude, enabledGlobs(files), enabledGlobs(search));
  };

  /** Artifacts live in the extension's own storage, never in the user's tree. */
  const outDirFor = (folder: vscode.WorkspaceFolder): string =>
    path.join((context.storageUri ?? context.globalStorageUri).fsPath, 'reports', folder.name);

  /**
   * Keep the newest few runs. The stem carries the run's timestamp, so sorting
   * the names descending groups each run's .json with its .html for free.
   */
  const prune = async (dir: string): Promise<void> => {
    try {
      const names = (await fs.promises.readdir(dir)).filter((n) => n.startsWith('gandalf-')).sort();
      const keep = new Set(
        [...new Set(names.map((n) => n.replace(/\.[^.]+$/, '')))].slice(-REPORTS_KEPT),
      );
      for (const name of names) {
        if (keep.has(name.replace(/\.[^.]+$/, ''))) continue;
        await fs.promises.rm(path.join(dir, name), { force: true });
      }
    } catch (err) {
      log().debug(`report pruning skipped: ${String(err)}`);
    }
  };

  const reportFailure = (err: unknown, job: Job): void => {
    if (err instanceof vscode.CancellationError) {
      log().info(`scan cancelled: ${jobLabel(job)}`);
      return;
    }
    if (err instanceof ScanSkippedError) {
      log().info(`scan skipped: ${err.message}`);
      return;
    }
    if (err instanceof GandalfNotFoundError) {
      log().error(err.message);
      if (notFoundShown) return;
      notFoundShown = true;
      void vscode.window
        .showErrorMessage(`Gandalf: ${err.message}`, 'Open settings')
        .then((choice) => {
          if (choice === 'Open settings') {
            void vscode.commands.executeCommand('workbench.action.openSettings', 'gandalf');
          }
        });
      return;
    }
    const message = err instanceof Error ? err.message : String(err);
    log().error(message);
    // Automatic scans fail quietly after the first notification — a broken tool
    // must not produce a popup on every save.
    if (job.manual || Date.now() - lastErrorAt > ERROR_COOLDOWN_MS) {
      lastErrorAt = Date.now();
      void vscode.window.showErrorMessage(`Gandalf: ${message}`, 'Show log').then((choice) => {
        if (choice === 'Show log') log().show(true);
      });
    }
  };

  const execute = async (job: Job, token: vscode.CancellationToken): Promise<void> => {
    const s = settingsFor(job.folder);
    const isProjectScope = job.kind !== 'file';

    // Hashed once: the answer to "did this change" is also what gets committed
    // if the run succeeds.
    const scanned = job.absPath ? await guard.inspect(job.absPath) : undefined;
    if (job.kind === 'file' && !job.manual && scanned?.unchanged) {
      log().debug(`unchanged since last scan, skipping: ${job.relPath}`);
      return;
    }

    scanning = jobLabel(job);
    findingsView.setScanning(jobLabel(job));
    statusBar.scanning(jobLabel(job));
    // One cache for the whole run: streaming normalizes gate by gate, and a
    // fresh cache per gate re-stats paths earlier gates already resolved.
    const paths = pathCache();
    // Streamed gates arrive in bursts; the tree is rebuilt on a short leash so
    // a 40-gate run doesn't mean 40 full re-renders back to back.
    let refreshAt = 0;
    let refreshTimer: NodeJS.Timeout | undefined;
    const refreshSoon = () => {
      if (refreshTimer) return;
      const wait = Math.max(0, refreshAt + 250 - Date.now());
      refreshTimer = setTimeout(() => {
        refreshTimer = undefined;
        refreshAt = Date.now();
        findingsView.refresh();
      }, wait);
    };
    const onProgress = (p: ScanProgress) => {
      statusBar.scanning(jobLabel(job), p);
      findingsView.setScanning(`${jobLabel(job)} · ${describeProgress(p)}`);
      job.report?.(p);
    };
    try {
      const outDir = outDirFor(job.folder);
      const excludes = excludesFor(job.folder, s);
      const result = await runGandalf(
        {
          folder: job.folder,
          kind: job.kind,
          relPath: job.relPath,
          commit: job.commit,
          llm: job.llm ?? s.llm,
          html: isProjectScope, // A one-file scorecard is not the report anyone wants.
          outDir,
          excludes,
          reason: job.reason,
          onProgress,
          onStart: () => store.beginStream(job.folder),
          onGate: (gate) => {
            store.pushStream(job.folder, gate.name, normalizeGate(gate, job.folder.uri.fsPath, paths));
            refreshSoon();
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
      if (job.kind === 'commit') {
        // A different scope entirely: it produces a report, not a new board.
        if (result.htmlPath) reportView.current = result.htmlPath;
      } else if (job.kind === 'file' && job.absPath) {
        store.setFile(job.folder, job.absPath, snapshot, result.durationMs);
      } else {
        store.setProject(job.folder, snapshot, result.durationMs);
        if (result.htmlPath) reportView.current = result.htmlPath;
      }
      // Only remembered on success — a failed scan must not suppress the retry.
      if (job.absPath && scanned) guard.commit(job.absPath, scanned.hash);
      publishDiagnostics();
      if (isProjectScope) logTimings(result.payload, result.durationMs);
      await prune(outDir);
    } catch (err) {
      reportFailure(err, job);
    } finally {
      clearTimeout(refreshTimer);
      // The report (or the failure) is now the whole truth — drop the partials.
      store.endStream(job.folder);
      scanning = undefined;
      findingsView.setScanning('');
      paint();
    }
  };

  /**
   * Where the time went. Gandalf records each gate's wall-clock in the payload,
   * so a slow scan can name its own culprits instead of leaving the user to
   * guess which of ~30 gates to disable.
   */
  const byDuration = (payload: Snapshot['payload'] | undefined) =>
    (payload?.gates ?? [])
      .filter((g) => typeof g.duration === 'number')
      .sort((a, b) => (b.duration ?? 0) - (a.duration ?? 0));

  const logTimings = (payload: Snapshot['payload'], totalMs: number): void => {
    const timed = byDuration(payload);
    if (timed.length === 0) return;
    const top = timed
      .slice(0, 5)
      .map((g) => `${g.name} ${(g.duration ?? 0).toFixed(1)}s`)
      .join(', ');
    log().info(`slowest gates (of ${timed.length}) in ${(totalMs / 1000).toFixed(1)}s: ${top}`);
  };

  const scheduler = new Scheduler(execute, () => {
    const s = settingsFor(primaryFolder());
    return { debounceMs: s.debounceMs, intervalMinutes: s.intervalMinutes };
  });

  const armSweep = () => {
    const s = settingsFor(primaryFolder());
    scheduler.setSweep(s.trigger === 'interval' || s.trigger === 'onSaveAndInterval', () => {
      const folder = primaryFolder();
      return folder
        ? { folder, kind: 'workspace' as ScanKind, reason: 'periodic sweep', manual: false }
        : undefined;
    });
  };

  const manualJob = (kind: ScanKind, extra: Partial<Job> = {}): Job | undefined => {
    const folder =
      kind === 'file'
        ? (() => {
            const doc = vscode.window.activeTextEditor?.document;
            return doc?.uri.scheme === 'file' ? vscode.workspace.getWorkspaceFolder(doc.uri) : undefined;
          })()
        : primaryFolder();
    if (!folder) {
      void vscode.window.showWarningMessage(
        kind === 'file'
          ? 'Gandalf: open a file inside a workspace folder first.'
          : 'Gandalf: open a folder to scan.',
      );
      return undefined;
    }
    const job: Job = { folder, kind, reason: 'command', manual: true, ...extra };
    if (kind === 'file') {
      const doc = vscode.window.activeTextEditor!.document;
      job.absPath = doc.uri.fsPath;
      job.relPath = path.relative(folder.uri.fsPath, doc.uri.fsPath);
    }
    return job;
  };

  const run = async (kind: ScanKind, extra: Partial<Job> = {}): Promise<boolean> => {
    const job = manualJob(kind, extra);
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
        token.onCancellationRequested(() => scheduler.cancelJob(job));
        return scheduler.runNow(job);
      },
    );
    return true;
  };

  const openReport = async (llm: boolean): Promise<void> => {
    const folder = primaryFolder();
    if (!folder) return;
    if (llm || !reportView.current || !fs.existsSync(reportView.current)) {
      const ok = await run('workspace', { llm: llm || undefined, reason: llm ? 'report + LLM summary' : 'report' });
      if (!ok) return;
    }
    if (!reportView.current) {
      void vscode.window.showWarningMessage('Gandalf: no report available — the scan did not complete.');
      return;
    }
    const snapshot = store.project(folder);
    await reportView.show(reportView.current, snapshot?.scope ?? folder.name);
  };

  context.subscriptions.push(
    findingsView.register(),
    findingsView,
    store.onDidChange(paint),
    store,
    diagnostics,
    statusBar,
    scheduler,
    { dispose: () => reportView.dispose() },
    { dispose: disposeLog },

    vscode.commands.registerCommand('gandalf.scanWorkspace', () => run('workspace')),
    vscode.commands.registerCommand('gandalf.scanCurrentFile', () => run('file')),
    vscode.commands.registerCommand('gandalf.showReport', () => openReport(false)),
    vscode.commands.registerCommand('gandalf.showReportWithLlm', () => openReport(true)),
    vscode.commands.registerCommand('gandalf.cancel', () => scheduler.cancel()),
    vscode.commands.registerCommand('gandalf.showLog', () => log().show(true)),
    vscode.commands.registerCommand('gandalf.filterCurrentFile', () => findingsView.setScope('file')),
    vscode.commands.registerCommand('gandalf.filterProject', () => findingsView.setScope('project')),
    vscode.commands.registerCommand('gandalf.filterFindings', () => findingsView.pickFilters()),
    vscode.commands.registerCommand('gandalf.expandAll', () => findingsView.expandAll()),
    vscode.commands.registerCommand('gandalf.showTimings', () => showTimings()),
    vscode.commands.registerCommand('gandalf.showHistory', () => showHistory()),
    vscode.commands.registerCommand('gandalf.exportReport', () => exportReport()),
    vscode.commands.registerCommand('gandalf.checkEnvironment', async () => {
      const folder = primaryFolder();
      if (folder) await runDoctor(folder, settingsFor(folder));
    }),
    vscode.commands.registerCommand('gandalf.buildToolsImage', async () => {
      const folder = primaryFolder();
      if (folder) await buildToolsImage(folder, settingsFor(folder));
    }),

    vscode.window.onDidChangeActiveTextEditor(() => findingsView.refresh()),
    vscode.workspace.onDidSaveTextDocument((doc) => onSave(doc)),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (!e.affectsConfiguration('gandalf')) return;
      resetLauncherCache();
      notFoundShown = false;
      armSweep();
      publishDiagnostics();
      paint();
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(armSweep),
  );

  /**
   * Per-gate timings, slowest first — the answer to "why does a full scan take
   * so long". Selecting gates copies a ready-to-paste skip list, since trimming
   * the gate set is the only real lever on a slow scan.
   */
  /**
   * Save the scorecard somewhere the user chooses — gandalf writes it into the
   * extension's storage, which is no use for attaching to a pull request.
   */
  async function exportReport(): Promise<void> {
    if (!reportView.current || !fs.existsSync(reportView.current)) {
      const ok = await run('workspace', { reason: 'export' });
      if (!ok || !reportView.current) return;
    }
    const folder = primaryFolder();
    const suggested = path.basename(reportView.current);
    const target = await vscode.window.showSaveDialog({
      defaultUri: vscode.Uri.file(path.join(folder?.uri.fsPath ?? os.homedir(), suggested)),
      filters: { 'HTML report': ['html'] },
      title: 'Export the Gandalf report',
    });
    if (!target) return;
    await fs.promises.copyFile(reportView.current, target.fsPath);
    const choice = await vscode.window.showInformationMessage(
      `Gandalf: report exported to ${path.basename(target.fsPath)}.`,
      'Open',
    );
    if (choice === 'Open') await vscode.env.openExternal(target);
  }

  /**
   * Score over time. `.gandalf-trend.jsonl` holds what CLI and CI runs recorded;
   * `git log` supplies the commits, including the ones nothing has scored yet,
   * because "we have never measured this" is part of the history too.
   */
  async function showHistory(): Promise<void> {
    const folder = primaryFolder();
    if (!folder) return;
    const root = folder.uri.fsPath;

    let trend = new Map<string, TrendEntry>();
    try {
      trend = parseTrend(await fs.promises.readFile(path.join(root, '.gandalf-trend.jsonl'), 'utf8'));
    } catch {
      // No log yet — the picker still lists commits, all unscored.
    }
    const log = await probe('git', ['log', '-40', '--format=%h%x1f%s%x1f%cs'], root);
    const commits: Commit[] = log.ok ? parseLog(log.output) : [];
    if (commits.length === 0) {
      void vscode.window.showInformationMessage('Gandalf: no commits to show a history for.');
      return;
    }

    // Oldest first for the sparkline and the deltas; newest first in the list.
    const scored = [...commits].reverse().filter((c) => trend.has(c.short));
    const line = sparkline(scored.map((c) => trend.get(c.short)!.score));
    const previous = new Map<string, number>();
    scored.forEach((c, i) => {
      if (i > 0) previous.set(c.short, trend.get(scored[i - 1].short)!.score);
    });

    const chosen = await vscode.window.showQuickPick(
      commits.map((c) => {
        const entry = trend.get(c.short);
        const change = entry ? delta(entry.score, previous.get(c.short)) : '';
        return {
          label: entry ? `${entry.score}/100${change ? `  ${change}` : ''}` : '— not scanned',
          description: `${c.short}  ${c.subject}`,
          detail: c.date,
          commit: c.short,
        };
      }),
      {
        title: scored.length
          ? `Score history — ${line} over ${scored.length} scanned commit(s) of ${commits.length}`
          : `Score history — nothing scanned yet of ${commits.length} commit(s)`,
        placeHolder: 'Pick a commit to scan it and open its report',
      },
    );
    if (chosen) {
      const ok = await run('commit', { commit: chosen.commit, reason: `commit ${chosen.commit}` });
      if (ok && reportView.current) await reportView.show(reportView.current, chosen.commit);
    }
  }

  async function showTimings(): Promise<void> {
    const folder = primaryFolder();
    const snapshot = folder ? store.project(folder) : undefined;
    const run = folder ? store.lastRun(folder) : undefined;
    const timed = byDuration(snapshot?.payload);
    if (!snapshot || timed.length === 0) {
      void vscode.window.showInformationMessage(
        'Gandalf: no timings yet — run “Gandalf: Scan Workspace” first.',
      );
      return;
    }
    const summed = timed.reduce((n, g) => n + (g.duration ?? 0), 0);
    const wall = (run?.durationMs ?? 0) / 1000;
    const chosen = await vscode.window.showQuickPick(
      timed.map((g) => ({
        label: g.name,
        description: `${(g.duration ?? 0).toFixed(1)}s`,
        detail: g.summary,
      })),
      {
        canPickMany: true,
        title: `Gate timings — ${wall.toFixed(1)}s wall clock, ${summed.toFixed(1)}s summed (gates run concurrently)`,
        placeHolder: 'Select gates to copy a .gandalf.toml skip list for editor scans',
      },
    );
    if (!chosen?.length) return;
    await vscode.env.clipboard.writeText(
      `[gandalf]\nskip = [${chosen.map((c) => `"${c.label}"`).join(', ')}]\n`,
    );
    void vscode.window.showInformationMessage(
      `Gandalf: copied a skip list for ${chosen.length} gate(s). Paste it into a .gandalf.toml and ` +
        'point `gandalf.configPath` at that file to use it for editor scans only.',
    );
  }

  function onSave(doc: vscode.TextDocument): void {
    if (doc.uri.scheme !== 'file') return;
    const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
    if (!folder) return;
    const s = settingsFor(folder);
    if (s.trigger !== 'onSave' && s.trigger !== 'onSaveAndInterval') return;

    const relPath = path.relative(folder.uri.fsPath, doc.uri.fsPath);
    // Never let gandalf's own output re-trigger gandalf.
    if (relPath.startsWith('..') || /^(reports|\.git)[/\\]/.test(relPath)) return;
    if (/^\.gandalf-(cache|trend|baseline)/.test(path.basename(relPath))) return;

    const job: Job = {
      folder,
      kind: 'file',
      reason: `saved ${relPath}`,
      manual: false,
    };
    if (job.kind === 'file') {
      job.relPath = relPath;
      job.absPath = doc.uri.fsPath;
    }
    scheduler.schedule(job);
  }

  armSweep();
  paint();

  const startup = settingsFor(primaryFolder());
  if (startup.scanOnStartup && startup.trigger !== 'manual') {
    // Let the window settle before forking ~30 gates.
    const timer = setTimeout(() => {
      const folder = primaryFolder();
      if (folder) scheduler.schedule({ folder, kind: 'workspace', reason: 'startup', manual: false });
    }, 5000);
    context.subscriptions.push({ dispose: () => clearTimeout(timer) });
  }

  log().info('Gandalf extension activated');
}

export function deactivate(): void {
  // Everything is registered in context.subscriptions.
}
