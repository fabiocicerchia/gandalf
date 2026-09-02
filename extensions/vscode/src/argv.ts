/**
 * The command line handed to gandalf.
 *
 * Three groups, three questions: what to scan, what to write, and how to run it.
 * Every flag an older build might not have is gated on what `--help` said —
 * argparse fails the whole run on a flag it does not know, so a build that
 * predates `--stream` must never be handed one.
 */
import * as vscode from 'vscode';

import { Settings } from './config';
import { GateEvent } from './events';
import { expand, Launcher, ScanKind } from './launcher';
import { ScanProgress } from './progress';

export interface RunRequest {
  folder: vscode.WorkspaceFolder;
  kind: ScanKind;
  /** Repo-relative path, for `kind === 'file'`. */
  relPath?: string;
  /** Commit to evaluate, for `kind === 'commit'`. */
  commit?: string;
  llm: boolean;
  html: boolean;
  outDir: string;
  /** Paths no gate should read, already translated to gandalf's dialect. */
  excludes: string[];
  /** Why this run started — shown in the log. */
  reason: string;
  /** Called as gandalf reports stages and gate completions. */
  onProgress?: (p: ScanProgress) => void;
  /** Called once the gate count is known, before any gate has finished. */
  onStart?: (gates: number, scope: string) => void;
  /** Called per gate as it finishes, when the build supports `--stream`. */
  onGate?: (gate: GateEvent) => void;
}

type Supports = (flag: string) => boolean;

/** What to scan. Nothing means the whole working tree, which is the default. */
function scopeArgs(req: RunRequest): string[] {
  if (req.kind === 'file' && req.relPath) return ['--path', req.relPath.replace(/\\/g, '/')];
  if (req.kind === 'commit' && req.commit) return ['--commit', req.commit];
  return [];
}

/** What to write: the summary, the report, and where they go. */
function outputArgs(req: RunRequest, supports: Supports): string[] {
  const args: string[] = [];
  if (!req.llm) args.push('--no-llm');
  if (!req.html) args.push('--no-html');
  if (supports('--out-dir')) args.push('--out-dir', req.outDir);
  // Editor scans never join the trend log: it is meant to be per-commit, and a
  // scan on every save would swamp it. Scanning a named commit is the exception
  // — that is exactly one entry for exactly one commit, which is what the log is.
  if (req.kind !== 'commit' && supports('--no-trend')) args.push('--no-trend');
  return args;
}

/** How to run it: the config, the concurrency, the cache and the stream. */
function runArgs(req: RunRequest, s: Settings, supports: Supports): string[] {
  const args: string[] = [];
  if (s.configPath) args.push('--config', expand(s.configPath));
  if (s.concurrency > 0) args.push('--concurrency', String(s.concurrency));
  // The cache is keyed per gate on a hash of the whole scanned file set, so a
  // one-file scan would overwrite the workspace entries with a one-file hash
  // and make the next full scan a complete miss. Only whole-tree scans cache.
  if (s.useCache && req.kind === 'workspace') args.push('--cache');
  // Per-gate results as they land, so the pane fills during the run.
  if ((req.onGate || req.onStart) && supports('--stream')) args.push('--stream');
  return args;
}

/**
 * Repeated rather than comma-joined: a path may legitimately contain a comma,
 * and argparse's append is unambiguous.
 */
function excludeArgs(req: RunRequest, supports: Supports): string[] {
  if (!supports('--exclude')) return [];
  return req.excludes.flatMap((pattern) => ['--exclude', pattern]);
}

export function buildArgs(req: RunRequest, s: Settings, l: Launcher): string[] {
  const supports: Supports = (flag) => l.flags.has(flag);
  return [
    ...l.args,
    ...scopeArgs(req),
    ...outputArgs(req, supports),
    ...runArgs(req, s, supports),
    ...excludeArgs(req, supports),
    // Last, so what the user asked for wins.
    ...s.extraArgs,
  ];
}
