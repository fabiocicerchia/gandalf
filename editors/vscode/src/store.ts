/**
 * What the panel, the diagnostics and the status bar all read from.
 *
 * Three tiers, newest winning, because they answer different questions:
 *  - a workspace/staged run is the project truth (verdict, score, every gate);
 *  - a file run is a fast refresh of one file, and only replaces that file's
 *    findings — everything else stays as the last project run left it;
 *  - a *stream* is the run in progress: gandalf reports each gate as it
 *    finishes (`--stream`), so those gates' findings replace what the last run
 *    said about them while the rest of the board stays up. The verdict and score
 *    are not part of this tier — they are properties of a whole run, and only
 *    the final report has them.
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
  /** Gates reported by the run currently in flight, keyed by gate name. */
  private streams = new Map<string, Map<string, Finding[]>>();

  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChange = this.changed.event;

  /** A run started reporting gates; its results supersede per-gate history. */
  beginStream(folder: vscode.WorkspaceFolder): void {
    this.streams.set(key(folder), new Map());
  }

  /**
   * Deliberately does not fire `onDidChange`: gates stream in bursts, and that
   * event means "a run settled". The caller repaints the pane on its own leash.
   */
  pushStream(folder: vscode.WorkspaceFolder, gate: string, findings: Finding[]): void {
    const stream = this.streams.get(key(folder));
    if (!stream) return; // The run was cancelled or superseded.
    stream.set(gate, findings);
  }

  /** The run ended — its report (or its failure) is now the whole truth. */
  endStream(folder: vscode.WorkspaceFolder): void {
    if (this.streams.delete(key(folder))) this.changed.fire();
  }

  streamedGates(folder: vscode.WorkspaceFolder): number {
    return this.streams.get(key(folder))?.size ?? 0;
  }

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

  /**
   * The board: the last project run, with per-file refreshes over the top, and
   * the in-flight run's gates over that.
   */
  findings(folder: vscode.WorkspaceFolder): Finding[] {
    const k = key(folder);
    const stream = this.streams.get(k);
    const perFile = this.files.get(k);
    const streamed = stream && stream.size > 0 ? stream : undefined;
    const fresh = (f: Finding) => !streamed?.has(f.gate);

    let merged = (this.projects.get(k)?.findings ?? []).filter(fresh);
    if (perFile && perFile.size > 0) {
      const paths = new Set(perFile.keys());
      merged = merged.filter((f) => !f.resolvedPath || !paths.has(f.resolvedPath));
      for (const entry of perFile.values()) merged.push(...entry.findings.filter(fresh));
    }
    if (streamed) for (const findings of streamed.values()) merged.push(...findings);
    return merged.sort(compareFindings);
  }

  folders(): vscode.WorkspaceFolder[] {
    const all = vscode.workspace.workspaceFolders ?? [];
    return all.filter(
      (f) => this.projects.has(key(f)) || this.files.has(key(f)) || this.streams.has(key(f)),
    );
  }

  clear(): void {
    this.projects.clear();
    this.files.clear();
    this.runs.clear();
    this.streams.clear();
    this.changed.fire();
  }

  dispose(): void {
    this.changed.dispose();
  }
}
