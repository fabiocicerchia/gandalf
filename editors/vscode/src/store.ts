/**
 * What the panel, the diagnostics and the status bar all read from.
 *
 * Two tiers, because the two scan scopes answer different questions:
 *  - a workspace/staged run is the project truth (verdict, score, every gate);
 *  - a file run is a fast refresh of one file, and only replaces that file's
 *    findings — everything else stays as the last project run left it.
 */
import * as vscode from 'vscode';

import { compareFindings } from './parse';
import { Finding, Snapshot } from './types';

export interface LastRun {
  scope: string;
  verdict: Snapshot['payload']['verdict'];
  score: number;
  at: number;
  durationMs: number;
}

function key(folder: vscode.WorkspaceFolder): string {
  return folder.uri.toString();
}

export class ResultStore {
  private projects = new Map<string, Snapshot>();
  private files = new Map<string, Map<string, { at: number; findings: Finding[] }>>();
  private runs = new Map<string, LastRun>();

  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChange = this.changed.event;

  setProject(folder: vscode.WorkspaceFolder, snapshot: Snapshot, durationMs: number): void {
    const k = key(folder);
    this.projects.set(k, snapshot);
    // A full run supersedes every per-file refresh that came before it.
    this.files.delete(k);
    this.runs.set(k, {
      scope: snapshot.scope,
      verdict: snapshot.payload.verdict,
      score: snapshot.payload.score,
      at: snapshot.at,
      durationMs,
    });
    this.changed.fire();
  }

  setFile(
    folder: vscode.WorkspaceFolder,
    absPath: string,
    snapshot: Snapshot,
    durationMs: number,
  ): void {
    const k = key(folder);
    let perFile = this.files.get(k);
    if (!perFile) this.files.set(k, (perFile = new Map()));
    // Keep only this file's findings: a file-scoped run still lets tree-scanning
    // gates (gitleaks, trivy, …) report elsewhere, and those rows belong to the
    // project run, which saw the whole tree.
    perFile.set(absPath, {
      at: snapshot.at,
      findings: snapshot.findings.filter((f) => f.resolvedPath === absPath),
    });
    this.runs.set(k, {
      scope: snapshot.scope,
      verdict: snapshot.payload.verdict,
      score: snapshot.payload.score,
      at: snapshot.at,
      durationMs,
    });
    this.changed.fire();
  }

  project(folder: vscode.WorkspaceFolder): Snapshot | undefined {
    return this.projects.get(key(folder));
  }

  lastRun(folder: vscode.WorkspaceFolder): LastRun | undefined {
    return this.runs.get(key(folder));
  }

  /** Project findings with any per-file refreshes merged over the top. */
  findings(folder: vscode.WorkspaceFolder): Finding[] {
    const perFile = this.files.get(key(folder));
    const base = this.projects.get(key(folder))?.findings ?? [];
    if (!perFile || perFile.size === 0) return base;
    const overridden = new Set(perFile.keys());
    const merged = base.filter((f) => !f.resolvedPath || !overridden.has(f.resolvedPath));
    for (const entry of perFile.values()) merged.push(...entry.findings);
    return merged.sort(compareFindings);
  }

  folders(): vscode.WorkspaceFolder[] {
    const all = vscode.workspace.workspaceFolders ?? [];
    return all.filter((f) => this.projects.has(key(f)) || this.files.has(key(f)));
  }

  clear(): void {
    this.projects.clear();
    this.files.clear();
    this.runs.clear();
    this.changed.fire();
  }

  dispose(): void {
    this.changed.dispose();
  }
}
