/**
 * Where a run's artifacts go, and what a run must not read.
 *
 * Both answers are about the user's tree: gandalf writes a .json and a .html per
 * run, and neither belongs in the repository being scanned; and a scan should
 * skip whatever the editor already hides, so the exclusion list is not asked for
 * twice.
 */
import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

import { Settings } from './config';
import { enabledGlobs, excludePatterns } from './exclude';
import { log } from './log';

/** Reports the extension wrote and still keeps, oldest pruned beyond this. */
const REPORTS_KEPT = 8;

/** Artifacts live in the extension's own storage, never in the user's tree. */
export function outDirFor(
  context: vscode.ExtensionContext,
  folder: vscode.WorkspaceFolder,
): string {
  const storage = context.storageUri ?? context.globalStorageUri;
  return path.join(storage.fsPath, 'reports', folder.name);
}

/**
 * Keep the newest few runs. The stem carries the run's timestamp, so sorting
 * the names descending groups each run's .json with its .html for free.
 */
export async function pruneReports(dir: string): Promise<void> {
  const stem = (name: string) => name.replace(/\.[^.]+$/, '');
  try {
    const names = (await fs.promises.readdir(dir)).filter((n) => n.startsWith('gandalf-')).sort();
    const keep = new Set([...new Set(names.map(stem))].slice(-REPORTS_KEPT));
    for (const name of names) {
      if (keep.has(stem(name))) continue;
      await fs.promises.rm(path.join(dir, name), { force: true });
    }
  } catch (err) {
    log().debug(`report pruning skipped: ${String(err)}`);
  }
}

/**
 * What this folder should not scan: the extension's own setting, plus whatever
 * the editor already hides. Read per run rather than cached — these are three
 * config lookups, and a stale exclusion list would scan a tree the user thought
 * they had excluded.
 */
export function excludesFor(folder: vscode.WorkspaceFolder, s: Settings): string[] {
  if (!s.useEditorExcludes) return excludePatterns(s.exclude);
  const files = vscode.workspace.getConfiguration('files', folder.uri).get('exclude');
  const search = vscode.workspace.getConfiguration('search', folder.uri).get('exclude');
  return excludePatterns(s.exclude, enabledGlobs(files), enabledGlobs(search));
}

/** Never let gandalf's own output re-trigger gandalf. */
export function scannable(relPath: string): boolean {
  if (relPath.startsWith('..') || /^(reports|\.git)[/\\]/.test(relPath)) return false;
  return !/^\.gandalf-(cache|trend|baseline)/.test(path.basename(relPath));
}
