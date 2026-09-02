/**
 * Running a child process, and killing all of it.
 *
 * gandalf shells out to the scanners (trivy, semgrep, docker), so what has to
 * die on a cancel or a timeout is the process group, not the python parent —
 * otherwise a cancelled scan leaves a trivy orphaned onto the extension host,
 * still pinning a core minutes later.
 */
import { spawn } from 'child_process';
import * as vscode from 'vscode';

const MAX_OUTPUT_CHARS = 4 * 1024 * 1024;
/** How long a signalled process group gets before it is killed outright. */
const SIGKILL_AFTER_MS = 3000;

export interface ExecOptions {
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
}

export interface ExecResult {
  code: number;
  stdout: string;
  stderr: string;
}

type Child = ReturnType<typeof spawn>;

/**
 * Signal the child's whole process group, falling back to the child alone when
 * the group is already gone or never formed.
 */
function signalGroup(child: Child, sig: NodeJS.Signals): void {
  try {
    if (process.platform === 'win32') {
      // No process groups: taskkill's /T walks the child tree instead.
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F']).unref();
      return;
    }
    if (child.pid) process.kill(-child.pid, sig);
  } catch {
    try {
      child.kill(sig);
    } catch {
      // Nothing left to signal.
    }
  }
}

/**
 * SIGTERM first so a dockerized gate gets a chance to tear its container down;
 * SIGKILL only if the process is still there a few seconds later. `hasExited`
 * rather than `child.killed`: that flag only says a signal was delivered, so it
 * is true immediately and the escalation never fired.
 */
function killGroup(child: Child, hasExited: () => boolean): void {
  signalGroup(child, 'SIGTERM');
  setTimeout(() => hasExited() || signalGroup(child, 'SIGKILL'), SIGKILL_AFTER_MS).unref?.();
}

export function exec(command: string, args: string[], opts: ExecOptions): Promise<ExecResult> {
  return new Promise((resolve, reject) => {
    let child: Child;
    try {
      // Its own process group: gandalf shells out to the scanners (trivy,
      // semgrep, docker), and signalling the python process alone leaves those
      // running as orphans of the extension host — a cancelled scan that keeps
      // burning a core. The group is what has to die, not the parent.
      child = spawn(command, args, {
        cwd: opts.cwd,
        env: opts.env,
        detached: process.platform !== 'win32',
      });
    } catch (err) {
      reject(err);
      return;
    }

    const out: string[] = [];
    const errOut: string[] = [];
    let outChars = 0;
    let errChars = 0;
    let settled = false;
    let exited = false;

    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      cancelSub?.dispose();
      fn();
    };

    const kill = () => killGroup(child, () => exited);

    const timer = setTimeout(() => {
      kill();
      finish(() => reject(new Error(`gandalf timed out after ${Math.round(opts.timeoutMs / 1000)}s`)));
    }, opts.timeoutMs);

    const cancelSub = opts.token?.onCancellationRequested(() => {
      kill();
      finish(() => reject(new vscode.CancellationError()));
    });

    // Decoded by the stream, not per chunk: a read boundary lands mid-UTF-8
    // sequence often enough on a big scan, and `buf.toString()` on each half
    // turns one `--stream` gate line into two unparsable ones. It also drops
    // the Buffer.concat of the whole output at the end.
    child.stdout?.setEncoding('utf8');
    child.stderr?.setEncoding('utf8');
    child.stdout?.on('data', (s: string) => {
      if (opts.collectStdout !== false && outChars < MAX_OUTPUT_CHARS) {
        out.push(s);
        outChars += s.length;
      }
      opts.onStdout?.(s);
    });
    child.stderr?.on('data', (s: string) => {
      if (errChars < MAX_OUTPUT_CHARS) {
        errOut.push(s);
        errChars += s.length;
      }
      opts.onStderr?.(s);
    });
    child.on('error', (err) => {
      exited = true;
      finish(() => reject(err));
    });
    child.on('exit', () => (exited = true));
    child.on('close', (code) =>
      finish(() => resolve({ code: code ?? -1, stdout: out.join(''), stderr: errOut.join('') })),
    );
  });
}
