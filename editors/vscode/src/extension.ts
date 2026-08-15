import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

import { readSettings, Settings } from './config';
import { DiagnosticGroup, DiagnosticPublisher } from './diagnostics';
import { buildToolsImage, runDoctor } from './doctor';
import { FindingsView } from './findingsView';
import { disposeLog, log } from './log';
import { normalize } from './parse';
import { ReportView } from './report';
import {
  GandalfNotFoundError,
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

export function activate(context: vscode.ExtensionContext): void {
  const store = new ResultStore();
  const diagnostics = new DiagnosticPublisher();
  const statusBar = new StatusBar();
  const reportView = new ReportView();
  const findingsView = new FindingsView(store);
  const guard = new ContentGuard();

  let lastErrorAt = 0;
  let notFoundShown = false;

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
    const s = settingsFor(folder);
    findingsView.refresh();
    statusBar.idle(
      folder ? store.lastRun(folder) : undefined,
      s.statusBarEnabled,
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

  /** Artifacts live in the extension's own storage, never in the user's tree. */
  const outDirFor = (folder: vscode.WorkspaceFolder, s: Settings): string => {
    if (s.reportsDirectory) {
      return path.isAbsolute(s.reportsDirectory)
        ? s.reportsDirectory
        : path.join(folder.uri.fsPath, s.reportsDirectory);
    }
    const base = context.storageUri ?? context.globalStorageUri;
    return path.join(base.fsPath, 'reports', folder.name);
  };

  /** Keep the newest `keep` runs (a run is its .json plus its .html). */
  const prune = async (dir: string, keep: number): Promise<void> => {
    try {
      const names = (await fs.promises.readdir(dir)).filter((n) => n.startsWith('gandalf-'));
      const stems = new Map<string, { files: string[]; mtime: number }>();
      for (const name of names) {
        const full = path.join(dir, name);
        const stem = name.replace(/\.[^.]+$/, '');
        const stat = await fs.promises.stat(full);
        const entry = stems.get(stem) ?? { files: [], mtime: 0 };
        entry.files.push(full);
        entry.mtime = Math.max(entry.mtime, stat.mtimeMs);
        stems.set(stem, entry);
      }
      const stale = [...stems.values()].sort((a, b) => b.mtime - a.mtime).slice(keep);
      for (const entry of stale) {
        for (const file of entry.files) await fs.promises.rm(file, { force: true });
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

    if (job.kind === 'file' && job.absPath && !job.manual && (await guard.unchanged(job.absPath))) {
      log().debug(`unchanged since last scan, skipping: ${job.relPath}`);
      return;
    }

    findingsView.setScanning(jobLabel(job));
    statusBar.scanning(jobLabel(job));
    // Hash the bytes we are about to scan, and only remember them if the run
    // succeeds — a failed scan must not suppress the next attempt.
    const scanned = job.absPath ? await guard.snapshot(job.absPath) : '';
    try {
      const outDir = outDirFor(job.folder, s);
      const result = await runGandalf(
        {
          folder: job.folder,
          kind: job.kind,
          relPath: job.relPath,
          llm: job.llm ?? s.llm,
          html: isProjectScope, // A one-file scorecard is not the report anyone wants.
          fix: job.fix,
          writeBaseline: job.writeBaseline,
          outDir,
          reason: job.reason,
        },
        s,
        token,
      );

      const snapshot: Snapshot = {
        payload: result.payload,
        findings: normalize(result.payload, job.folder.uri.fsPath),
        jsonPath: result.jsonPath,
        htmlPath: result.htmlPath,
        scope: result.payload.scope,
        at: Date.now(),
      };
      if (job.kind === 'file' && job.absPath) {
        store.setFile(job.folder, job.absPath, snapshot, result.durationMs);
      } else {
        store.setProject(job.folder, snapshot, result.durationMs);
        if (result.htmlPath) reportView.current = result.htmlPath;
      }
      if (job.absPath && scanned) guard.commit(job.absPath, scanned);
      publishDiagnostics();
      await prune(outDir, s.reportsKeep);
    } catch (err) {
      reportFailure(err, job);
    } finally {
      findingsView.setScanning('');
      paint();
    }
  };

  const scheduler = new Scheduler(execute, () => {
    const s = settingsFor(primaryFolder());
    return { debounceMs: s.debounceMs, idleMs: s.idleMs, intervalMinutes: s.intervalMinutes };
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
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Window, title: `Gandalf: scanning ${jobLabel(job)}` },
      () => scheduler.runNow(job),
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

  const confirm = async (title: string, detail: string): Promise<boolean> => {
    const choice = await vscode.window.showWarningMessage(title, { modal: true, detail }, 'Run');
    return choice === 'Run';
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
    vscode.commands.registerCommand('gandalf.scanStaged', () => run('staged')),
    vscode.commands.registerCommand('gandalf.showReport', () => openReport(false)),
    vscode.commands.registerCommand('gandalf.showReportWithLlm', () => openReport(true)),
    vscode.commands.registerCommand('gandalf.cancel', () => scheduler.cancel()),
    vscode.commands.registerCommand('gandalf.showLog', () => log().show(true)),
    vscode.commands.registerCommand('gandalf.clearResults', () => {
      store.clear();
      diagnostics.clear();
      guard.forget();
      paint();
    }),
    vscode.commands.registerCommand('gandalf.filterCurrentFile', () => findingsView.setScope('file')),
    vscode.commands.registerCommand('gandalf.filterProject', () => findingsView.setScope('project')),
    vscode.commands.registerCommand('gandalf.filterSeverity', () => findingsView.pickSeverities()),
    vscode.commands.registerCommand('gandalf.applyFixes', async () => {
      const ok = await confirm(
        'Gandalf: apply gate autofixes?',
        'Runs gandalf --fix, which rewrites files in the working tree (ruff --fix, ruff format, eslint --fix).',
      );
      if (ok) await run('workspace', { fix: true, reason: 'apply fixes' });
    }),
    vscode.commands.registerCommand('gandalf.writeBaseline', async () => {
      const ok = await confirm(
        'Gandalf: accept every current finding as the baseline?',
        'Writes .gandalf-baseline.json in the repository root. Findings recorded there stop failing the gate, so only new ones can.',
      );
      if (ok) await run('workspace', { writeBaseline: true, reason: 'write baseline' });
    }),
    vscode.commands.registerCommand('gandalf.checkEnvironment', async () => {
      const folder = primaryFolder();
      if (folder) await runDoctor(folder, settingsFor(folder));
    }),
    vscode.commands.registerCommand('gandalf.buildToolsImage', async () => {
      const folder = primaryFolder();
      if (folder) await buildToolsImage(folder, settingsFor(folder));
    }),

    vscode.workspace.onDidChangeTextDocument(() => scheduler.noteEdit()),
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
      kind: s.scopeOnSave === 'file' ? 'file' : s.scopeOnSave === 'staged' ? 'staged' : 'workspace',
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
