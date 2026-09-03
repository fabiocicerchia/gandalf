/**
 * "Can gandalf run here at all?"
 *
 * Deliberately not a tool-by-tool inventory. Gandalf already answers that,
 * per gate, on every scan — a gate whose tool is missing says so in its summary,
 * and the pane counts those as "could not run". Repeating the list here meant
 * keeping a copy of `plugins.IMAGE_TOOLS` in TypeScript and watching it drift.
 *
 * What a scan *cannot* tell you is why it produced nothing at all, so that is
 * what this checks: gandalf itself, git, docker, the scanner image, the LLM
 * endpoint the judge gates call. Reading the checks and offering something to do
 * about them are separate steps, because only the second one has a dialog in it.
 */
import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

import { Settings } from './config';
import { log } from './log';
import { findOnPath, GandalfNotFoundError, probe, promptInstall, resolveLauncher } from './runner';

/** Same default gandalf uses, overridable the same way. */
const toolsImage = (): string => process.env.GANDALF_TOOLS_IMAGE || 'gandalf-tools';

const LLM_URL = (): string =>
  (process.env.GANDALF_LLM_URL ?? 'http://127.0.0.1:8787/v1').replace(/\/$/, '');

const LLM_TIMEOUT_MS = 3000;

interface Check {
  ok: boolean;
  text: string;
}

/** What was checked, plus the two answers the offer below is built from. */
interface Diagnosis {
  checks: Check[];
  /** Set when gandalf itself could not be located — nothing else matters then. */
  missing?: GandalfNotFoundError;
  docker: string;
  hasImage: boolean;
  git: string;
}

async function llmReachable(): Promise<Check> {
  const url = LLM_URL();
  try {
    const res = await fetch(`${url}/models`, { signal: AbortSignal.timeout(LLM_TIMEOUT_MS) });
    return { ok: res.ok, text: `${url} — HTTP ${res.status}` };
  } catch (err) {
    return { ok: false, text: `${url} — ${err instanceof Error ? err.message : String(err)}` };
  }
}

/** Can gandalf be found, and does it run? */
async function checkGandalf(
  folder: vscode.WorkspaceFolder,
  s: Settings,
): Promise<{ check: Check; missing?: GandalfNotFoundError }> {
  try {
    const launcher = await resolveLauncher(folder, s);
    const ran = await probe(launcher.command, [...launcher.args, '--help'], folder.uri.fsPath);
    return { check: { ok: ran.ok, text: `gandalf: ${launcher.label}` } };
  } catch (err) {
    const text = `gandalf: ${err instanceof Error ? err.message : String(err)}`;
    return {
      check: { ok: false, text },
      missing: err instanceof GandalfNotFoundError ? err : undefined,
    };
  }
}

async function diagnose(folder: vscode.WorkspaceFolder, s: Settings): Promise<Diagnosis> {
  const image = toolsImage();
  const { check: gandalf, missing } = await checkGandalf(folder, s);

  const git = findOnPath('git');
  const isRepo = fs.existsSync(path.join(folder.uri.fsPath, '.git'));
  // Most gates fall back to this image when their tool is not on PATH, so its
  // absence is the single biggest reason a board is full of skipped gates.
  const docker = findOnPath('docker');
  const hasImage = docker
    ? (await probe(docker, ['image', 'inspect', image], folder.uri.fsPath)).ok
    : false;
  // The judge gates call this whatever the summary setting says. Editor scans
  // cap the retries at 1, so a dead endpoint costs a second rather than eleven.
  const llm = await llmReachable();

  return {
    missing,
    docker,
    hasImage,
    git,
    checks: [
      gandalf,
      { ok: Boolean(git), text: git ? `git: ${git}` : 'git: not on PATH — no scope to resolve' },
      {
        ok: isRepo,
        text: `workspace: ${folder.uri.fsPath}${isRepo ? '' : ' is not a git repository'}`,
      },
      { ok: Boolean(docker), text: docker ? `docker: ${docker}` : 'docker: not on PATH' },
      {
        ok: hasImage,
        text: hasImage
          ? `scanner tools: "${image}" present`
          : `scanner tools: "${image}" missing — most gates will report their tool unavailable`,
      },
      { ok: llm.ok, text: `LLM endpoint (judge gates): ${llm.text}` },
    ],
  };
}

/**
 * Something to *do* about each missing dependency, most actionable first — "see
 * the log" is not an answer to "docker is not installed". git and docker have no
 * one command that is right on every platform, so those open the official
 * instructions rather than guessing at a package manager.
 */
function offers(d: Diagnosis): string[] {
  const actions: string[] = [];
  if (d.docker && !d.hasImage) actions.push('Build tools image');
  if (!d.git) actions.push('Install git');
  if (!d.docker) actions.push('Install docker');
  actions.push('Show log');
  return actions;
}

async function act(choice: string | undefined): Promise<void> {
  if (choice === 'Build tools image') await vscode.commands.executeCommand('gandalf.buildToolsImage');
  if (choice === 'Install git') {
    await vscode.env.openExternal(vscode.Uri.parse('https://git-scm.com/downloads'));
  }
  if (choice === 'Install docker') {
    await vscode.env.openExternal(vscode.Uri.parse('https://docs.docker.com/get-started/get-docker/'));
  }
  if (choice === 'Show log') log().show(true);
}

export async function runDoctor(folder: vscode.WorkspaceFolder, s: Settings): Promise<void> {
  const d = await diagnose(folder, s);
  log().info(
    '— Gandalf environment —\n' + d.checks.map((c) => `  ${c.ok ? '✔' : '✖'} ${c.text}`).join('\n'),
  );

  // Nothing else on the list matters if gandalf itself is absent — offer the
  // command that fixes that instead of a summary of everything it can't reach.
  if (d.missing) return promptInstall(d.missing.message);

  const failed = d.checks.filter((c) => !c.ok);
  const headline = failed.length
    ? failed.map((c) => c.text.split(':')[0]).join(', ') + ' — see the log'
    : 'Everything gandalf needs is available.';
  const actions = offers(d);
  const choice = await (failed.length
    ? vscode.window.showWarningMessage(`Gandalf: ${headline}`, ...actions)
    : vscode.window.showInformationMessage(`Gandalf: ${headline}`, ...actions));
  await act(choice);
}

/**
 * Build the scanner-tools image in a terminal — it is a multi-minute,
 * output-heavy docker build, which belongs somewhere the user can watch and
 * interrupt it rather than behind a progress spinner.
 */
export async function buildToolsImage(folder: vscode.WorkspaceFolder, s: Settings): Promise<void> {
  let checkout = '';
  try {
    checkout = (await resolveLauncher(folder, s)).checkout;
  } catch (err) {
    if (err instanceof GandalfNotFoundError) {
      void promptInstall(err.message);
      return;
    }
    throw err;
  }
  if (!checkout || !fs.existsSync(path.join(checkout, 'tools.Dockerfile'))) {
    void vscode.window.showErrorMessage(
      'Gandalf: the tools image is built from `tools.Dockerfile` in a gandalf checkout. ' +
        'Set `gandalf.path` to one, then run this again.',
    );
    return;
  }
  const terminal = vscode.window.createTerminal({ name: 'gandalf: build tools', cwd: checkout });
  terminal.show(true);
  terminal.sendText(`docker build -f tools.Dockerfile -t ${toolsImage()} .`);
}
