/**
 * Locating gandalf and running it.
 *
 * gandalf is pure-stdlib Python with no install step, so "where is it" has
 * several legitimate answers: `gandalf.path` (a wrapper or a checkout), a
 * checkout in the open workspace, `gandalf` on PATH, or the clone `install.sh`
 * drops in `~/.local/share/gandalf`. All are tried, in that order.
 */
import { spawn } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import * as vscode from 'vscode';

import { Settings } from './config';
import { EventParser, GateEvent } from './events';
import { log } from './log';
import { ProgressParser, ScanProgress } from './progress';
import { Payload } from './types';

export class GandalfNotFoundError extends Error {}
/** Raised when a scan cannot apply, but nothing is wrong (e.g. untracked file). */
export class ScanSkippedError extends Error {}

export interface Launcher {
  command: string;
  args: string[];
  env: NodeJS.ProcessEnv;
  /** Human-readable description of how gandalf is being invoked. */
  label: string;
  /** Source checkout backing this launcher, when there is one (for `make tools`). */
  checkout: string;
  /** Flags this build of gandalf accepts, read from `--help`. */
  flags: Set<string>;
}

export type ScanKind = 'workspace' | 'file' | 'commit';

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

export interface RunResult {
  payload: Payload;
  jsonPath: string;
  htmlPath: string;
  exitCode: number;
  durationMs: number;
}

const MAX_OUTPUT_BYTES = 4 * 1024 * 1024;
/** The scorecard and the report paths are a few KB; this is only a backstop. */
const MAX_PLAIN_CHARS = 256 * 1024;
const HELP_TIMEOUT_MS = 20_000;

let launcherCache = new Map<string, Launcher>();

export function resetLauncherCache(): void {
  launcherCache = new Map();
}

function expand(p: string): string {
  return p.startsWith('~') ? path.join(os.homedir(), p.slice(1)) : p;
}

function isCheckout(dir: string): boolean {
  if (!dir) return false;
  try {
    return fs.statSync(path.join(dir, 'src', 'gandalf', '__main__.py')).isFile();
  } catch {
    return false;
  }
}

function findOnPath(name: string): string {
  const exts = process.platform === 'win32' ? (process.env.PATHEXT ?? '.EXE;.CMD;.BAT').split(';') : [''];
  for (const dir of (process.env.PATH ?? '').split(path.delimiter)) {
    if (!dir) continue;
    for (const ext of exts) {
      const candidate = path.join(dir, name + ext);
      try {
        if (fs.statSync(candidate).isFile()) return candidate;
      } catch {
        // Next candidate.
      }
    }
  }
  return '';
}

function exec(
  command: string,
  args: string[],
  opts: {
    cwd?: string;
    env?: NodeJS.ProcessEnv;
    timeoutMs: number;
    token?: vscode.CancellationToken;
    /** Receives stderr as it arrives, for live progress. */
    onStderr?: (chunk: string) => void;
    /** Receives stdout as it arrives, for streamed gate results. */
    onStdout?: (chunk: string) => void;
    /** When false, stdout is handed to `onStdout` only and never buffered. */
    collectStdout?: boolean;
  },
): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(command, args, { cwd: opts.cwd, env: opts.env });
    } catch (err) {
      reject(err);
      return;
    }

    const out: Buffer[] = [];
    const errOut: Buffer[] = [];
    let outBytes = 0;
    let errBytes = 0;
    let settled = false;

    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      cancelSub?.dispose();
      fn();
    };

    // SIGTERM first so a dockerized gate gets a chance to tear its container
    // down; SIGKILL only if the process is still there a few seconds later.
    const kill = () => {
      child.kill('SIGTERM');
      setTimeout(() => child.killed || child.kill('SIGKILL'), 3000).unref?.();
    };

    const timer = setTimeout(() => {
      kill();
      finish(() => reject(new Error(`gandalf timed out after ${Math.round(opts.timeoutMs / 1000)}s`)));
    }, opts.timeoutMs);

    const cancelSub = opts.token?.onCancellationRequested(() => {
      kill();
      finish(() => reject(new vscode.CancellationError()));
    });

    child.stdout?.on('data', (b: Buffer) => {
      if (opts.collectStdout !== false && outBytes < MAX_OUTPUT_BYTES) {
        out.push(b);
        outBytes += b.length;
      }
      opts.onStdout?.(b.toString('utf8'));
    });
    child.stderr?.on('data', (b: Buffer) => {
      if (errBytes < MAX_OUTPUT_BYTES) {
        errOut.push(b);
        errBytes += b.length;
      }
      opts.onStderr?.(b.toString('utf8'));
    });
    child.on('error', (err) => finish(() => reject(err)));
    child.on('close', (code) =>
      finish(() =>
        resolve({
          code: code ?? -1,
          stdout: Buffer.concat(out).toString('utf8'),
          stderr: Buffer.concat(errOut).toString('utf8'),
        }),
      ),
    );
  });
}

async function readFlags(l: Omit<Launcher, 'flags'>, cwd: string): Promise<Set<string>> {
  try {
    const { stdout, stderr } = await exec(l.command, [...l.args, '--help'], {
      cwd,
      env: l.env,
      timeoutMs: HELP_TIMEOUT_MS,
    });
    return new Set((stdout + stderr).match(/--[a-z][a-z0-9-]*/g) ?? []);
  } catch (err) {
    log().warn(`could not read gandalf --help (${String(err)}); assuming a current build`);
    return new Set(['--out-dir', '--no-trend', '--cache', '--concurrency', '--path']);
  }
}

/** Every plausible way to invoke gandalf, most explicit first. */
function candidates(folder: vscode.WorkspaceFolder, s: Settings): Omit<Launcher, 'flags'>[] {
  const out: Omit<Launcher, 'flags'>[] = [];
  const viaPython = (dir: string, label: string) => ({
    command: s.pythonPath,
    args: ['-m', 'gandalf'],
    env: {
      ...process.env,
      PYTHONPATH: [path.join(dir, 'src'), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
    },
    label: `${s.pythonPath} -m gandalf (${label}: ${dir})`,
    checkout: dir,
  });

  // One setting for both shapes: a checkout is a directory we can recognise, so
  // there is no need to make the user say which kind of path they gave us.
  const configured = s.path ? expand(s.path) : '';
  if (isCheckout(configured)) out.push(viaPython(configured, 'gandalf.path'));
  else if (configured) {
    out.push({
      command: configured,
      args: [],
      env: { ...process.env },
      label: `gandalf.path: ${configured}`,
      checkout: '',
    });
  }
  if (isCheckout(folder.uri.fsPath)) out.push(viaPython(folder.uri.fsPath, 'workspace checkout'));
  const onPath = findOnPath('gandalf');
  if (onPath) {
    out.push({ command: onPath, args: [], env: { ...process.env }, label: `gandalf on PATH: ${onPath}`, checkout: '' });
  }
  const installed = path.join(os.homedir(), '.local', 'share', 'gandalf');
  if (isCheckout(installed)) out.push(viaPython(installed, 'install.sh clone'));
  return out;
}

export async function resolveLauncher(folder: vscode.WorkspaceFolder, s: Settings): Promise<Launcher> {
  const key = folder.uri.toString();
  const cached = launcherCache.get(key);
  if (cached) return cached;

  const options = candidates(folder, s);
  if (options.length === 0) {
    throw new GandalfNotFoundError(
      'Gandalf was not found. Install the wrapper with `make install`, or set `gandalf.checkoutPath` to a gandalf checkout.',
    );
  }
  const chosen = options[0];
  const launcher: Launcher = { ...chosen, flags: await readFlags(chosen, folder.uri.fsPath) };
  log().info(`using ${launcher.label}`);
  launcherCache.set(key, launcher);
  return launcher;
}

function buildArgs(req: RunRequest, s: Settings, l: Launcher): string[] {
  const args = [...l.args];
  const supports = (flag: string) => l.flags.has(flag);

  if (req.kind === 'file' && req.relPath) args.push('--path', req.relPath.replace(/\\/g, '/'));
  if (req.kind === 'commit' && req.commit) args.push('--commit', req.commit);

  if (!req.llm) args.push('--no-llm');
  if (!req.html) args.push('--no-html');

  if (supports('--out-dir')) args.push('--out-dir', req.outDir);
  // Editor scans never join the trend log: it is meant to be per-commit, and a
  // scan on every save would swamp it. Scanning a named commit is the exception
  // — that is exactly one entry for exactly one commit, which is what the log is.
  if (req.kind !== 'commit' && supports('--no-trend')) args.push('--no-trend');
  if (s.configPath) args.push('--config', expand(s.configPath));
  if (s.concurrency > 0) args.push('--concurrency', String(s.concurrency));

  // The cache is keyed per gate on a hash of the whole scanned file set, so a
  // one-file scan would overwrite the workspace entries with a one-file hash
  // and make the next full scan a complete miss. Only whole-tree scans cache.
  if (s.useCache && req.kind === 'workspace') args.push('--cache');

  // Per-gate results as they land, so the pane fills during the run.
  if ((req.onGate || req.onStart) && supports('--stream')) args.push('--stream');

  // Repeated rather than comma-joined: a path may legitimately contain a comma,
  // and argparse's append is unambiguous.
  if (supports('--exclude')) for (const pattern of req.excludes) args.push('--exclude', pattern);

  args.push(...s.extraArgs);
  return args;
}

const JSON_LINE = /^JSON report:\s*(.+)$/m;
const HTML_LINE = /^HTML report:\s*(.+)$/m;
/** gandalf's ways of saying the requested scope holds nothing to scan. */
const EMPTY_SCOPE = /no git-tracked files under this folder|every path under it is excluded/i;

function tail(text: string, lines = 12): string {
  return text.trimEnd().split('\n').slice(-lines).join('\n');
}

export async function runGandalf(
  req: RunRequest,
  s: Settings,
  token: vscode.CancellationToken,
): Promise<RunResult> {
  const launcher = await resolveLauncher(req.folder, s);
  const args = buildArgs(req, s, launcher);
  const started = Date.now();

  await fs.promises.mkdir(req.outDir, { recursive: true });
  log().info(`scan (${req.reason}): ${launcher.command} ${args.join(' ')}`);

  // The progress line and real stderr share the stream, so the parser splits
  // them: progress drives the UI, the rest is what an error report quotes.
  const progress = new ProgressParser();
  const events = new EventParser();
  let diagnostics = '';
  // Only the non-event stdout is kept: the scorecard and the two report paths.
  // Capped because it is a diagnostic aid, not a document.
  let plain = '';
  const { code, stderr } = await exec(launcher.command, args, {
    cwd: req.folder.uri.fsPath,
    env: {
      ...launcher.env,
      // Progress is TTY-gated; this turns it on for a piped child.
      GANDALF_PROGRESS: '1',
      // The skill-backed gates call the LLM whatever --no-llm says, and retry
      // with backoff when it is unreachable. gandalf's default of 3 is right for
      // CI and costs 11s per scan in an editor; one retry still absorbs a blip.
      GANDALF_LLM_RETRIES: process.env.GANDALF_LLM_RETRIES ?? '1',
    },
    timeoutMs: s.timeoutSeconds * 1000,
    token,
    onStderr: (chunk) => {
      const { progress: state, noise } = progress.feed(chunk);
      diagnostics += noise;
      if (state) req.onProgress?.(state);
    },
    collectStdout: false,
    onStdout: (chunk) => {
      const { events: found, text } = events.feed(chunk);
      plain += text;
      if (plain.length > MAX_PLAIN_CHARS) plain = plain.slice(-MAX_PLAIN_CHARS);
      for (const event of found) {
        if (event.event === 'start') req.onStart?.(event.gates, event.scope);
        else req.onGate?.(event);
      }
    },
  });
  plain += events.flush();
  diagnostics += progress.flush();

  if (EMPTY_SCOPE.test(stderr)) {
    throw new ScanSkippedError(`${req.relPath ?? req.kind}: nothing in scope to scan`);
  }

  const jsonMatch = JSON_LINE.exec(plain);
  if (!jsonMatch) {
    // Exit 1 is a red verdict (normal); anything without a report is a real error.
    const detail = diagnostics || stderr;
    log().error(`gandalf produced no report (exit ${code})\n${tail(detail || plain)}`);
    throw new Error(`gandalf failed (exit ${code}): ${tail(detail || plain, 3) || 'no output'}`);
  }

  const jsonPath = jsonMatch[1].trim();
  const htmlPath = (HTML_LINE.exec(plain)?.[1] ?? '').trim();
  const payload = JSON.parse(await fs.promises.readFile(jsonPath, 'utf8')) as Payload;
  const durationMs = Date.now() - started;
  log().info(
    `scan done in ${(durationMs / 1000).toFixed(1)}s — ${payload.verdict.toUpperCase()} ${payload.score}/100`,
  );
  return { payload, jsonPath, htmlPath, exitCode: code, durationMs };
}

/** Free-standing command runner, for the doctor and the tools-image build. */
export async function probe(
  command: string,
  args: string[],
  cwd?: string,
  timeoutMs = 15_000,
): Promise<{ ok: boolean; output: string }> {
  try {
    const { code, stdout, stderr } = await exec(command, args, { cwd, env: process.env, timeoutMs });
    return { ok: code === 0, output: (stdout || stderr).trim() };
  } catch (err) {
    return { ok: false, output: err instanceof Error ? err.message : String(err) };
  }
}

export { findOnPath };
