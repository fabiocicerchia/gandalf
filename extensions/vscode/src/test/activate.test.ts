/**
 * What activate() wires up.
 *
 * The contract an extension has with the editor is declarative — the command
 * ids, the view, the listeners — and every one of them lives in package.json as
 * well as in the code. These tests read package.json and hold activate() to it,
 * so a command that stops being registered fails here rather than in a bug
 * report about a menu entry that does nothing.
 */
import * as assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, it } from 'node:test';

import { activate, deactivate } from '../extension';
import {
  configuration,
  created,
  diagnosticCollections,
  executedCommands,
  listeners,
  logLines,
  notifications,
  quickPick,
  registeredCommands,
  resetShim,
  workspace,
} from './vscode-shim';

const manifest = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'),
) as { contributes: { commands: { command: string }[]; views: Record<string, { id: string }[]> } };

let context: { subscriptions: { dispose(): unknown }[]; storageUri: { fsPath: string } };
let storage: string;

const start = () => {
  activate(context as never);
};

beforeEach(() => {
  resetShim();
  // Nothing in these tests wants a scan five seconds after activation.
  configuration.gandalf = { 'scan.onStartup': false };
  storage = fs.mkdtempSync(path.join(os.tmpdir(), 'gandalf-activate-'));
  context = { subscriptions: [], storageUri: { fsPath: storage } };
});

afterEach(() => {
  for (const d of context.subscriptions.reverse()) d.dispose();
  deactivate();
  fs.rmSync(storage, { recursive: true, force: true });
});

describe('activation', () => {
  it('registers exactly the commands package.json contributes', () => {
    start();
    assert.deepEqual(
      [...registeredCommands.keys()].sort(),
      manifest.contributes.commands.map((c) => c.command).sort(),
    );
  });

  it('creates the findings view package.json declares, and only that one', () => {
    start();
    assert.deepEqual(created.treeViews, [manifest.contributes.views.gandalf[0].id]);
  });

  it('seeds the scope context the view/title menus are written against', () => {
    start();
    const seeded = executedCommands.filter((c) => c.id === 'setContext');
    assert.deepEqual(seeded[0].args, ['gandalf.scope', 'project']);
  });

  it('takes one status bar item and one diagnostic collection, not one per folder', () => {
    workspace.workspaceFolders = [
      { uri: { fsPath: '/a', toString: () => 'file:///a' }, name: 'a' },
      { uri: { fsPath: '/b', toString: () => 'file:///b' }, name: 'b' },
    ];
    start();
    assert.equal(created.statusBarItems.length, 1);
    assert.equal(diagnosticCollections.length, 1);
  });

  it('listens for the four editor events the scan policy is driven by', () => {
    start();
    for (const event of [
      'onDidChangeActiveTextEditor',
      'onDidSaveTextDocument',
      'onDidChangeConfiguration',
      'onDidChangeWorkspaceFolders',
    ]) {
      assert.equal(listeners[event]?.length, 1, `no listener on ${event}`);
    }
  });

  it('puts everything it created on the context, and disposes cleanly', () => {
    start();
    const item = created.statusBarItems[0];
    assert.ok(context.subscriptions.length >= registeredCommands.size);
    for (const d of context.subscriptions) d.dispose();
    context.subscriptions = [];
    assert.equal(item.disposed, 1);
  });

  it('paints the status bar before any scan has run', () => {
    start();
    assert.match(created.statusBarItems[0].text, /Gandalf/);
    assert.ok(created.statusBarItems[0].shown > 0);
  });

  it('says it activated, so the log names the moment the extension came up', () => {
    start();
    assert.ok(logLines.includes('info Gandalf extension activated'));
  });
});

describe('the commands, with nothing open', () => {
  const run = async (id: string): Promise<unknown> => {
    const handler = registeredCommands.get(id);
    assert.ok(handler, `${id} was never registered`);
    return handler();
  };

  it('asks for a folder rather than scanning nothing', async () => {
    start();
    await run('gandalf.scanWorkspace');
    assert.deepEqual(
      notifications.map((n) => n.message),
      ['Gandalf: open a folder to scan.'],
    );
  });

  it('asks for a file rather than scanning the wrong scope', async () => {
    start();
    await run('gandalf.scanCurrentFile');
    assert.deepEqual(
      notifications.map((n) => n.message),
      ['Gandalf: open a file inside a workspace folder first.'],
    );
  });

  it('says there are no timings yet instead of offering an empty picker', async () => {
    start();
    await run('gandalf.showTimings');
    assert.match(notifications[0].message, /no timings yet/);
    assert.equal(quickPick.lastItems.length, 0);
  });

  it('does not run the doctor when there is nothing for it to check', async () => {
    start();
    await run('gandalf.checkEnvironment');
    assert.deepEqual(notifications, []);
  });

  it('shows the log on request', async () => {
    start();
    await run('gandalf.showLog');
    assert.ok(logLines.includes('show'));
  });

  it('switches the pane scope, and tells the editor so the title bar follows', async () => {
    start();
    await run('gandalf.filterCurrentFile');
    const scopes = executedCommands.filter((c) => c.id === 'setContext').map((c) => c.args[1]);
    assert.deepEqual(scopes, ['project', 'file']);
    await run('gandalf.filterProject');
    assert.equal(
      executedCommands.filter((c) => c.id === 'setContext').at(-1)?.args[1],
      'project',
    );
  });

  it('opens no report and asks for none when there is no folder', async () => {
    start();
    await run('gandalf.showReport');
    assert.deepEqual(notifications, []);
  });
});

describe('a configuration change', () => {
  it('repaints without a scan when the change was not ours', () => {
    start();
    const before = created.statusBarItems[0].shown;
    listeners.onDidChangeConfiguration[0]({ affectsConfiguration: () => false } as never);
    assert.equal(created.statusBarItems[0].shown, before);
  });

  it('repaints when the change was ours', () => {
    start();
    const before = created.statusBarItems[0].shown;
    listeners.onDidChangeConfiguration[0]({ affectsConfiguration: () => true } as never);
    assert.ok(created.statusBarItems[0].shown > before);
  });
});

/**
 * Which saves reach the scheduler.
 *
 * A real git repository, and `gandalf.path` pointed at a path that does not
 * exist so the scan fails the moment it is launched: the run is observed by the
 * `scan (saved …)` line the launcher logs, which is the first thing that happens
 * once a job survives the filter. The debounce is set to its 250ms floor, so
 * `settled()` waiting twice that is long enough for a job that was scheduled to
 * have reached the launcher.
 */
describe('a saved document', () => {
  let repo: string;

  const save = (relPath: string, scheme = 'file'): void => {
    void listeners.onDidSaveTextDocument[0]({
      uri: { fsPath: path.join(repo, relPath), scheme },
    } as never);
  };

  const scansLogged = (): string[] =>
    logLines.filter((l) => l.includes('scan (saved ')).map((l) => l.replace(/^.*scan \(saved /, '').replace(/\).*$/, ''));

  /** Long enough for anything the save scheduled to have reached the launcher. */
  const settled = (): Promise<unknown> => new Promise((r) => setTimeout(r, 600));

  /** Wait for the launcher to log the run for `relPath`, or fail the test. */
  const awaitScanOf = async (relPath: string): Promise<void> => {
    for (let i = 0; i < 200 && !scansLogged().includes(relPath); i += 1) {
      await new Promise((r) => setTimeout(r, 25));
    }
    assert.deepEqual(scansLogged(), [relPath]);
  };

  /** Save it, wait past the debounce, and expect the scheduler to have ignored it. */
  const expectIgnored = async (relPath: string, scheme = 'file'): Promise<void> => {
    save(relPath, scheme);
    await settled();
    assert.deepEqual(scansLogged(), []);
  };

  beforeEach(() => {
    repo = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'gandalf-repo-')));
    fs.mkdirSync(path.join(repo, 'src'));
    fs.mkdirSync(path.join(repo, 'reports'));
    fs.writeFileSync(path.join(repo, 'src', 'a.py'), 'x = 1\n');
    fs.writeFileSync(path.join(repo, 'src', 'tracked.py'), 'y = 2\n');
    fs.writeFileSync(path.join(repo, '.gandalf-cache.json'), '{}\n');
    fs.writeFileSync(path.join(repo, 'reports', 'r.json'), '{}\n');
    fs.writeFileSync(path.join(repo, 'untracked.py'), 'z = 3\n');
    const git = (...args: string[]) => execFileSync('git', args, { cwd: repo, stdio: 'ignore' });
    git('init', '-q');
    git('config', 'user.email', 't@example.invalid');
    git('config', 'user.name', 'test');
    git('add', 'src', 'reports', '.gandalf-cache.json');
    git('commit', '-qm', 'init');

    configuration.gandalf = {
      'scan.onStartup': false,
      'scan.trigger': 'onSave',
      'scan.debounceMs': 250,
      // Nothing at this path, so the run fails at launch instead of scanning.
      path: path.join(repo, 'no-such-gandalf'),
    };
    workspace.workspaceFolders = [
      { uri: { fsPath: repo, toString: () => `file://${repo}` }, name: 'repo' },
    ];
    workspace.getWorkspaceFolder = () => workspace.workspaceFolders[0];
  });

  afterEach(() => {
    workspace.getWorkspaceFolder = () => undefined;
    fs.rmSync(repo, { recursive: true, force: true });
  });

  it('scans a tracked file that was saved', async () => {
    start();
    save('src/a.py');
    await awaitScanOf('src/a.py');
  });

  it('never lets a report gandalf wrote re-trigger gandalf', async () => {
    start();
    await expectIgnored('reports/r.json');
  });

  it('never lets gandalf’s own cache re-trigger gandalf', async () => {
    start();
    await expectIgnored('.gandalf-cache.json');
  });

  it('leaves a document that is not a file on disk alone', async () => {
    start();
    await expectIgnored('src/tracked.py', 'untitled');
  });

  it('leaves a file git does not track alone, since gandalf would find nothing', async () => {
    start();
    await expectIgnored('untracked.py');
  });

  it('does not scan on save when the trigger says scans are manual', async () => {
    configuration.gandalf = { ...configuration.gandalf, 'scan.trigger': 'manual' };
    start();
    await expectIgnored('src/a.py');
  });
});
