/**
 * Running gandalf once, and reading what it said.
 *
 * The three parts this used to hold are their own modules now — `exec.ts` for
 * the child process, `launcher.ts` for finding gandalf, `argv.ts` for the
 * command line — and they are re-exported from here, because the extension and
 * its tests are written against `./runner` and that spelling is not worth
 * churning.
 */
import * as fs from 'fs';
import * as vscode from 'vscode';

import { buildArgs, RunRequest } from './argv';
import { Settings } from './config';
import { EventParser } from './events';
import { exec } from './exec';
import { resolveLauncher } from './launcher';
import { log } from './log';
import { ProgressParser } from './progress';
import { Payload } from './types';

export { buildArgs, RunRequest } from './argv';
export {
  findOnPath,
  GandalfNotFoundError,
  INSTALL_COMMAND,
  Launcher,
  promptInstall,
  resetLauncherCache,
  resolveLauncher,
  ScanKind,
} from './launcher';

/** Raised when a scan cannot apply, but nothing is wrong (e.g. untracked file). */
export class ScanSkippedError extends Error {}

export interface RunResult {
  payload: Payload;
  jsonPath: string;
  htmlPath: string;
  exitCode: number;
  durationMs: number;
}

/** The scorecard and the report paths are a few KB; this is only a backstop. */
const MAX_PLAIN_CHARS = 256 * 1024;
const PROBE_TIMEOUT_MS = 15_000;
/** Lines of diagnostics quoted when a run produced no report. */
const TAIL_LINES = 12;

const JSON_LINE = /^JSON report:\s*(.+)$/m;
const HTML_LINE = /^HTML report:\s*(.+)$/m;
/** gandalf's ways of saying the requested scope holds nothing to scan. */
const EMPTY_SCOPE = /no git-tracked files under this folder|every path under it is excluded/i;

function tail(text: string, lines = TAIL_LINES): string {
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
  timeoutMs = PROBE_TIMEOUT_MS,
): Promise<{ ok: boolean; output: string }> {
  try {
    const { code, stdout, stderr } = await exec(command, args, { cwd, env: process.env, timeoutMs });
    return { ok: code === 0, output: (stdout || stderr).trim() };
  } catch (err) {
    return { ok: false, output: err instanceof Error ? err.message : String(err) };
  }
}
