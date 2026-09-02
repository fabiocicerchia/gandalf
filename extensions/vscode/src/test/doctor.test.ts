/**
 * "Can gandalf run here at all?"
 *
 * The doctor's answer is two things the user sees: a written report in the log,
 * and a notification whose buttons are the things that would fix it. Both are
 * asserted here. Which of docker, git and the LLM endpoint happen to be present
 * is a property of the machine running the suite, so nothing below asserts their
 * verdicts — only that each is checked, and that the offer made matches the
 * verdicts that were reached.
 */
import * as assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, it } from 'node:test';

import { Settings } from '../config';
import { buildToolsImage, runDoctor } from '../doctor';
import { resetLauncherCache } from '../runner';
import {
  created,
  executedCommands,
  logLines,
  notificationAnswer,
  notifications,
  openedExternal,
  resetShim,
} from './vscode-shim';

/** The gandalf checkout this extension lives in — a launcher can be built from it. */
const CHECKOUT = path.resolve(__dirname, '..', '..', '..');

const settings = (over: Partial<Settings> = {}): Settings => ({
  path: '',
  pythonPath: 'python3',
  configPath: '',
  extraArgs: [],
  exclude: [],
  useEditorExcludes: true,
  trigger: 'onSave',
  debounceMs: 1500,
  intervalMinutes: 15,
  scanOnStartup: true,
  timeoutSeconds: 600,
  concurrency: 0,
  useCache: true,
  llm: false,
  diagnosticsEnabled: true,
  minSeverity: 'info',
  ...over,
});

const folderAt = (fsPath: string) =>
  ({ uri: { fsPath, toString: () => `file://${fsPath}` }, name: path.basename(fsPath), index: 0 }) as never;

/** The report the doctor wrote, as the user would read it in the log. */
const report = (): string => logLines.filter((l) => l.includes('Gandalf environment')).join('\n');

let tmp: string;
let savedEnv: Record<string, string | undefined>;

beforeEach(() => {
  resetShim();
  resetLauncherCache();
  tmp = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'gandalf-doctor-')));
  savedEnv = { ...process.env };
  // A tools image nobody has, so "the image is missing" is the same answer on
  // every machine rather than a property of the developer's docker.
  process.env.GANDALF_TOOLS_IMAGE = 'gandalf-tools-absent-from-this-machine';
});

afterEach(() => {
  for (const key of Object.keys(process.env)) if (!(key in savedEnv)) delete process.env[key];
  Object.assign(process.env, savedEnv);
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('the environment report', () => {
  it('checks each thing a scan cannot report on for itself, and no tool inventory', async () => {
    await runDoctor(folderAt(tmp), settings({ path: path.join(tmp, 'no-such-gandalf') }));
    const lines = report().split('\n');
    assert.equal(lines.length, 7); // the heading, then one line per check
    for (const subject of ['gandalf:', 'git:', 'workspace:', 'docker:', 'scanner tools:', 'LLM endpoint']) {
      assert.ok(
        lines.some((l) => l.includes(subject)),
        `nothing in the report about ${subject}`,
      );
    }
  });

  it('marks a gandalf that will not run, and says so in the notification', async () => {
    await runDoctor(folderAt(tmp), settings({ path: path.join(tmp, 'no-such-gandalf') }));
    assert.match(report(), /✖ gandalf: gandalf\.path/);
    assert.equal(notifications.length, 1);
    assert.equal(notifications[0].kind, 'warning');
    assert.match(notifications[0].message, /^Gandalf: gandalf(, |$)/);
    assert.match(notifications[0].message, /see the log$/);
  });

  it('names the directory it judged, and calls out one that is not a repository', async () => {
    await runDoctor(folderAt(tmp), settings({ path: path.join(tmp, 'no-such-gandalf') }));
    assert.ok(report().includes(`✖ workspace: ${tmp} is not a git repository`));
  });

  it('always offers the log, and it opens', async () => {
    notificationAnswer.value = 'Show log';
    await runDoctor(folderAt(tmp), settings({ path: path.join(tmp, 'no-such-gandalf') }));
    assert.equal(notifications[0].actions.at(-1), 'Show log');
    assert.ok(logLines.includes('show'));
  });

  it('offers to build the missing image rather than explaining docker', async () => {
    notificationAnswer.value = 'Build tools image';
    await runDoctor(folderAt(tmp), settings({ path: path.join(tmp, 'no-such-gandalf') }));
    const hasDocker = report().includes('✔ docker: ');
    assert.equal(notifications[0].actions.includes('Build tools image'), hasDocker);
    assert.deepEqual(
      executedCommands.map((c) => c.id),
      hasDocker ? ['gandalf.buildToolsImage'] : [],
    );
  });

  it('sends someone with no git to the official instructions, not to a package manager', async () => {
    notificationAnswer.value = 'Install git';
    process.env.PATH = '';
    await runDoctor(folderAt(tmp), settings({ path: path.join(tmp, 'no-such-gandalf') }));
    assert.ok(notifications[0].actions.includes('Install git'));
    assert.deepEqual(openedExternal, ['https://git-scm.com/downloads']);
  });

  it('offers the install command instead of a summary when gandalf is absent entirely', async () => {
    // No PATH to find it on, and a HOME with no install.sh clone under it.
    process.env.PATH = '';
    process.env.HOME = tmp;
    await runDoctor(folderAt(tmp), settings());
    assert.equal(notifications.length, 1);
    assert.equal(notifications[0].kind, 'error');
    assert.match(notifications[0].message, /install\.sh \| bash/);
    assert.deepEqual(notifications[0].actions, ['Install Gandalf', 'Copy command', 'Open settings']);
  });
});

describe('building the scanner tools image', () => {
  it('runs the build in a terminal, from the checkout that owns the Dockerfile', async () => {
    await buildToolsImage(folderAt(CHECKOUT), settings());
    assert.deepEqual(
      created.terminals.map((t) => t.name),
      ['gandalf: build tools'],
    );
    assert.deepEqual(created.terminals[0].sent, [
      'docker build -f tools.Dockerfile -t gandalf-tools-absent-from-this-machine .',
    ]);
  });

  it('explains where the image comes from rather than failing silently', async () => {
    await buildToolsImage(folderAt(tmp), settings({ path: path.join(tmp, 'no-such-gandalf') }));
    assert.deepEqual(created.terminals, []);
    assert.equal(notifications[0].kind, 'error');
    assert.match(notifications[0].message, /tools\.Dockerfile.*gandalf\.path/s);
  });
});
