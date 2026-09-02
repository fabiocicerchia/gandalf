/**
 * Locating gandalf.
 *
 * gandalf is pure-stdlib Python with no install step, so "where is it" has
 * several legitimate answers: `gandalf.path` (a wrapper or a checkout), a
 * checkout in the open workspace, `gandalf` on PATH, or the clone `install.sh`
 * drops in `~/.local/share/gandalf`. All are tried, in that order, and the
 * winner is asked what flags it takes before anything is run through it.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import * as vscode from 'vscode';

import { Settings } from './config';
import { exec } from './exec';
import { log } from './log';

export class GandalfNotFoundError extends Error {}

/** The one-liner from the README — kept here so the notification can run it. */
export const INSTALL_COMMAND =
  'curl -fsSL https://raw.githubusercontent.com/fabiocicerchia/gandalf/main/install.sh | bash';

const HELP_TIMEOUT_MS = 20_000;

/** Flags assumed when `--help` could not be read at all. */
const ASSUMED_FLAGS = ['--out-dir', '--no-trend', '--cache', '--concurrency', '--path'];

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

let launcherCache = new Map<string, Launcher>();

export function resetLauncherCache(): void {
  launcherCache = new Map();
}

/**
 * "gandalf is missing" told once, the same way, wherever it is noticed — with
 * the command that fixes it rather than a pointer to a document that has it.
 */
export async function promptInstall(message: string): Promise<void> {
  const choice = await vscode.window.showErrorMessage(
    `Gandalf: ${message}`,
    'Install Gandalf',
    'Copy command',
    'Open settings',
  );
  if (choice === 'Install Gandalf') {
    const terminal = vscode.window.createTerminal('gandalf: install');
    terminal.show(true);
    terminal.sendText(INSTALL_COMMAND);
    // The clone and the wrapper take a moment; the next scan should look again
    // rather than trust the "not found" we just cached.
    resetLauncherCache();
  } else if (choice === 'Copy command') {
    await vscode.env.clipboard.writeText(INSTALL_COMMAND);
  } else if (choice === 'Open settings') {
    await vscode.commands.executeCommand('workbench.action.openSettings', 'gandalf');
  }
}

/** `~` is the shell's, not argparse's: expand it before anything is passed on. */
export function expand(p: string): string {
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

export function findOnPath(name: string): string {
  const exts =
    process.platform === 'win32' ? (process.env.PATHEXT ?? '.EXE;.CMD;.BAT').split(';') : [''];
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
    return new Set(ASSUMED_FLAGS);
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

export async function resolveLauncher(
  folder: vscode.WorkspaceFolder,
  s: Settings,
): Promise<Launcher> {
  const key = folder.uri.toString();
  const cached = launcherCache.get(key);
  if (cached) return cached;

  const options = candidates(folder, s);
  if (options.length === 0) {
    throw new GandalfNotFoundError(
      `the gandalf CLI is not installed. Install it now?  It runs:  ${INSTALL_COMMAND}` +
        `  — or point "gandalf.path" at an existing wrapper or checkout.`,
    );
  }
  const chosen = options[0];
  const launcher: Launcher = { ...chosen, flags: await readFlags(chosen, folder.uri.fsPath) };
  log().info(`using ${launcher.label}`);
  launcherCache.set(key, launcher);
  return launcher;
}
