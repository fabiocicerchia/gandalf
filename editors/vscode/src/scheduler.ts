/**
 * When scans are allowed to happen.
 *
 * A gandalf run forks ~30 gates, several of which are `docker run`. That is not
 * something to do on a keystroke, so every trigger funnels through here and the
 * following rules:
 *
 *  - **debounce** — a burst of saves collapses into one run;
 *  - **idle gate** — optionally wait for the editor to be quiet first;
 *  - **single flight** — exactly one gandalf process at a time, ever;
 *  - **coalescing** — while one runs, only the newest request survives to be
 *    run next, so a save storm never queues a backlog;
 *  - **preemption** — a manual run cancels an automatic one already in flight;
 *  - **content guard** — a file whose bytes are unchanged since its last scan
 *    is not rescanned at all (VS Code fires didSave on unmodified saves);
 *  - **focus gate** — periodic sweeps skip while the window is in the
 *    background, so a laptop left open doesn't sweep all afternoon.
 */
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as vscode from 'vscode';

import { log } from './log';
import { ScanProgress } from './progress';
import { ScanKind } from './runner';

export interface Job {
  folder: vscode.WorkspaceFolder;
  kind: ScanKind;
  relPath?: string;
  absPath?: string;
  llm?: boolean;
  fix?: boolean;
  writeBaseline?: boolean;
  reason: string;
  /** User-initiated: preempts an automatic run and ignores the idle gate. */
  manual: boolean;
  /** Set by a caller showing its own progress UI for this job. */
  report?: (p: ScanProgress) => void;
}

export function jobKey(job: Job): string {
  return `${job.folder.uri.toString()}|${job.kind}|${job.relPath ?? ''}`;
}

export function jobLabel(job: Job): string {
  if (job.kind === 'file') return job.relPath ?? 'file';
  if (job.kind === 'staged') return 'staged changes';
  return job.folder.name;
}

/** Remembers what a file looked like when it was last scanned. */
export class ContentGuard {
  private hashes = new Map<string, string>();

  private async hash(absPath: string): Promise<string> {
    const buf = await fs.promises.readFile(absPath);
    return crypto.createHash('sha1').update(buf).digest('hex');
  }

  /** True when the file is byte-identical to the last *successful* scan of it. */
  async unchanged(absPath: string): Promise<boolean> {
    const known = this.hashes.get(absPath);
    if (!known) return false;
    try {
      return (await this.hash(absPath)) === known;
    } catch {
      return false;
    }
  }

  /** Hash of what a run is about to scan. Pair with `commit` once it succeeds. */
  async snapshot(absPath: string): Promise<string> {
    try {
      return await this.hash(absPath);
    } catch {
      return '';
    }
  }

  commit(absPath: string, hash: string): void {
    this.hashes.set(absPath, hash);
  }

  forget(): void {
    this.hashes.clear();
  }
}

export class Scheduler {
  private timer?: NodeJS.Timeout;
  private sweep?: NodeJS.Timeout;
  private pending?: Job;
  private active?: { job: Job; source: vscode.CancellationTokenSource };
  private lastEditAt = 0;
  private lastCompletedAt = 0;
  /** Serializes every run, so `runNow` resolves when *its* job is done. */
  private chain: Promise<void> = Promise.resolve();

  constructor(
    private readonly execute: (job: Job, token: vscode.CancellationToken) => Promise<void>,
    private readonly settings: () => { debounceMs: number; idleMs: number; intervalMinutes: number },
  ) {}

  noteEdit(): void {
    this.lastEditAt = Date.now();
  }

  /** Queue a job behind the debounce timer. The newest request for a scope wins. */
  schedule(job: Job): void {
    if (this.pending && this.pending.manual && !job.manual) return;
    this.pending = job;
    this.arm(this.settings().debounceMs);
  }

  /**
   * Run now: cancels an automatic run in flight and skips the idle gate. The
   * returned promise resolves when *this* job is done, so a caller that needs
   * the result (opening the report) can await it.
   */
  runNow(job: Job): Promise<void> {
    if (this.active && !this.active.job.manual) {
      log().info(`preempting ${jobLabel(this.active.job)} for ${job.reason}`);
      this.active.source.cancel();
    }
    return this.start(job);
  }

  cancel(): void {
    clearTimeout(this.timer);
    this.timer = undefined;
    this.pending = undefined;
    this.active?.source.cancel();
  }

  /** Cancel one job, whether it is running or still queued. */
  cancelJob(job: Job): void {
    if (this.active?.job === job) this.active.source.cancel();
    if (this.pending === job) this.pending = undefined;
  }

  /** (Re)arm the periodic sweep. `factory` returns undefined when there's nothing to sweep. */
  setSweep(enabled: boolean, factory: () => Job | undefined): void {
    clearInterval(this.sweep);
    this.sweep = undefined;
    if (!enabled) return;
    const periodMs = this.settings().intervalMinutes * 60_000;
    this.sweep = setInterval(() => {
      if (!vscode.window.state.focused) {
        log().debug('sweep skipped — window not focused');
        return;
      }
      if (Date.now() - this.lastCompletedAt < periodMs * 0.9) return; // Already fresh.
      const job = factory();
      if (job) this.schedule(job);
    }, periodMs);
  }

  private arm(delayMs: number): void {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.fire(), Math.max(0, delayMs));
  }

  private async fire(): Promise<void> {
    const job = this.pending;
    if (!job) return;

    const { idleMs } = this.settings();
    if (idleMs > 0 && !job.manual) {
      const quietFor = Date.now() - this.lastEditAt;
      if (quietFor < idleMs) {
        this.arm(idleMs - quietFor);
        return;
      }
    }
    if (this.active) return; // Picked up when the current run finishes.

    this.pending = undefined;
    await this.start(job);
  }

  private start(job: Job): Promise<void> {
    const run = this.chain.then(async () => {
      const source = new vscode.CancellationTokenSource();
      this.active = { job, source };
      try {
        await this.execute(job, source.token);
      } finally {
        source.dispose();
        this.active = undefined;
        this.lastCompletedAt = Date.now();
        if (this.pending) this.arm(0);
      }
    });
    // The chain must survive a failed run, or every later job inherits the
    // rejection and nothing ever runs again.
    this.chain = run.catch(() => undefined);
    return run;
  }

  dispose(): void {
    clearTimeout(this.timer);
    clearInterval(this.sweep);
    this.active?.source.cancel();
  }
}
