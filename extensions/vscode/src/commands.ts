/**
 * Every command the extension contributes, in one table.
 *
 * The ids here and the ids in package.json's `contributes.commands` are the same
 * list twice — a table makes that a diff anyone can read, instead of fifteen
 * `registerCommand` calls buried in the activation sequence.
 *
 * The three commands with a body of their own are the ones that ask a question:
 * the timings picker, the history picker and the export dialog. Everything else
 * is one call into the session.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import * as vscode from 'vscode';

import { buildToolsImage, runDoctor } from './doctor';
import { Commit, delta, parseLog, parseTrend, sparkline, TrendEntry } from './history';
import { log } from './log';
import { gatesByDuration } from './parse';
import { probe } from './runner';
import { Session } from './session';

/** Commits `git log` is asked for when drawing the score history. */
const HISTORY_COMMITS = 40;

export function commandHandlers(session: Session): Record<string, () => unknown> {
  return {
    'gandalf.scanWorkspace': () => session.run('workspace'),
    'gandalf.scanCurrentFile': () => session.run('file'),
    'gandalf.showReport': () => session.openReport(false),
    'gandalf.showReportWithLlm': () => session.openReport(true),
    'gandalf.cancel': () => session.scheduler.cancel(),
    'gandalf.showLog': () => log().show(true),
    'gandalf.filterCurrentFile': () => session.findingsView.setScope('file'),
    'gandalf.filterProject': () => session.findingsView.setScope('project'),
    'gandalf.filterFindings': () => session.findingsView.pickFilters(),
    'gandalf.expandAll': () => session.findingsView.expandAll(),
    'gandalf.showTimings': () => showTimings(session),
    'gandalf.showHistory': () => showHistory(session),
    'gandalf.exportReport': () => exportReport(session),
    'gandalf.checkEnvironment': () => forFolder(session, runDoctor),
    'gandalf.buildToolsImage': () => forFolder(session, buildToolsImage),
  };
}

/** The commands that need somewhere to run do nothing when there is nowhere. */
async function forFolder(
  session: Session,
  action: (folder: vscode.WorkspaceFolder, s: ReturnType<Session['settingsFor']>) => Promise<void>,
): Promise<void> {
  const folder = session.primaryFolder();
  if (folder) await action(folder, session.settingsFor(folder));
}

/**
 * Per-gate timings, slowest first — the answer to "why does a full scan take so
 * long". Selecting gates copies a ready-to-paste skip list, since trimming the
 * gate set is the only real lever on a slow scan.
 */
async function showTimings(session: Session): Promise<void> {
  const folder = session.primaryFolder();
  const snapshot = folder ? session.store.project(folder) : undefined;
  const lastRun = folder ? session.store.lastRun(folder) : undefined;
  const timed = gatesByDuration(snapshot?.payload);
  if (!snapshot || timed.length === 0) {
    void vscode.window.showInformationMessage(
      'Gandalf: no timings yet — run “Gandalf: Scan Workspace” first.',
    );
    return;
  }
  const summed = timed.reduce((n, g) => n + (g.duration ?? 0), 0);
  const wall = (lastRun?.durationMs ?? 0) / 1000;
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

/** The scores in `.gandalf-trend.jsonl`, or an empty history when there is none. */
async function readTrend(root: string): Promise<Map<string, TrendEntry>> {
  try {
    return parseTrend(await fs.promises.readFile(path.join(root, '.gandalf-trend.jsonl'), 'utf8'));
  } catch {
    // No log yet — the picker still lists commits, all unscored.
    return new Map();
  }
}

/** One quick pick item per commit, scored ones carrying their change. */
function historyItems(
  commits: Commit[],
  trend: Map<string, TrendEntry>,
  previous: Map<string, number>,
) {
  return commits.map((c) => {
    const entry = trend.get(c.short);
    const change = entry ? delta(entry.score, previous.get(c.short)) : '';
    return {
      label: entry ? `${entry.score}/100${change ? `  ${change}` : ''}` : '— not scanned',
      description: `${c.short}  ${c.subject}`,
      detail: c.date,
      commit: c.short,
    };
  });
}

/**
 * Score over time. `.gandalf-trend.jsonl` holds what CLI and CI runs recorded;
 * `git log` supplies the commits, including the ones nothing has scored yet,
 * because "we have never measured this" is part of the history too.
 */
async function showHistory(session: Session): Promise<void> {
  const folder = session.primaryFolder();
  if (!folder) return;
  const root = folder.uri.fsPath;

  const trend = await readTrend(root);
  const gitLog = await probe('git', ['log', `-${HISTORY_COMMITS}`, '--format=%h%x1f%s%x1f%cs'], root);
  const commits: Commit[] = gitLog.ok ? parseLog(gitLog.output) : [];
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

  const chosen = await vscode.window.showQuickPick(historyItems(commits, trend, previous), {
    title: scored.length
      ? `Score history — ${line} over ${scored.length} scanned commit(s) of ${commits.length}`
      : `Score history — nothing scanned yet of ${commits.length} commit(s)`,
    placeHolder: 'Pick a commit to scan it and open its report',
  });
  if (!chosen) return;
  const ok = await session.run('commit', {
    commit: chosen.commit,
    reason: `commit ${chosen.commit}`,
  });
  if (ok && session.reportView.current) {
    await session.reportView.show(session.reportView.current, chosen.commit);
  }
}

/**
 * Save the scorecard somewhere the user chooses — gandalf writes it into the
 * extension's storage, which is no use for attaching to a pull request.
 */
async function exportReport(session: Session): Promise<void> {
  if (!session.reportView.current || !fs.existsSync(session.reportView.current)) {
    const ok = await session.run('workspace', { reason: 'export' });
    if (!ok || !session.reportView.current) return;
  }
  const folder = session.primaryFolder();
  const suggested = path.basename(session.reportView.current);
  const target = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(path.join(folder?.uri.fsPath ?? os.homedir(), suggested)),
    filters: { 'HTML report': ['html'] },
    title: 'Export the Gandalf report',
  });
  if (!target) return;
  await fs.promises.copyFile(session.reportView.current, target.fsPath);
  const choice = await vscode.window.showInformationMessage(
    `Gandalf: report exported to ${path.basename(target.fsPath)}.`,
    'Open',
  );
  if (choice === 'Open') await vscode.env.openExternal(target);
}
