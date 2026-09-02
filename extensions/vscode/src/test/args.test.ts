/**
 * The command line the extension hands gandalf.
 *
 * Every flag here is a decision with a reason behind it — the cache is only
 * safe on a whole-tree scan, the trend log is per-commit, a flag an older build
 * does not have must not be passed at all — and none of them are visible from
 * anywhere but the argv itself. So the argv is what is asserted.
 */
import * as assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { Settings } from '../config';
import { buildArgs, Launcher, RunRequest, ScanKind } from '../runner';

const ALL_FLAGS = ['--out-dir', '--no-trend', '--cache', '--concurrency', '--path', '--stream', '--exclude'];

const launcher = (flags: string[] = ALL_FLAGS): Launcher => ({
  command: 'python3',
  args: ['-m', 'gandalf'],
  env: {},
  label: 'test',
  checkout: '',
  flags: new Set(flags),
});

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

const request = (kind: ScanKind, over: Partial<RunRequest> = {}): RunRequest => ({
  folder: { uri: { fsPath: '/repo' }, name: 'repo', index: 0 } as never,
  kind,
  llm: false,
  html: kind !== 'file',
  outDir: '/out',
  excludes: [],
  reason: 'test',
  ...over,
});

const valueAfter = (args: string[], flag: string): string | undefined =>
  args[args.indexOf(flag) + 1];

describe('the gandalf command line', () => {
  it('keeps the launcher’s own arguments in front', () => {
    const args = buildArgs(request('workspace'), settings(), launcher());
    assert.deepEqual(args.slice(0, 2), ['-m', 'gandalf']);
  });

  it('scopes a file scan with --path, in gandalf’s slash direction', () => {
    const args = buildArgs(request('file', { relPath: 'src\\a.py' }), settings(), launcher());
    assert.equal(valueAfter(args, '--path'), 'src/a.py');
  });

  it('scopes a commit scan with --commit and nothing else', () => {
    const args = buildArgs(request('commit', { commit: 'abc1234' }), settings(), launcher());
    assert.equal(valueAfter(args, '--commit'), 'abc1234');
    assert.ok(!args.includes('--path'));
  });

  it('caches only a whole-tree scan', () => {
    // The cache is keyed on a hash of the whole scanned file set: a one-file
    // scan would overwrite the workspace entries and make the next full scan
    // a complete miss.
    const s = settings({ useCache: true });
    assert.ok(buildArgs(request('workspace'), s, launcher()).includes('--cache'));
    assert.ok(!buildArgs(request('file', { relPath: 'a.py' }), s, launcher()).includes('--cache'));
    assert.ok(!buildArgs(request('commit', { commit: 'a' }), s, launcher()).includes('--cache'));
  });

  it('honours the setting that switches the cache off', () => {
    const args = buildArgs(request('workspace'), settings({ useCache: false }), launcher());
    assert.ok(!args.includes('--cache'));
  });

  it('keeps editor scans out of the trend log, and lets a named commit in', () => {
    assert.ok(buildArgs(request('workspace'), settings(), launcher()).includes('--no-trend'));
    assert.ok(buildArgs(request('file', { relPath: 'a.py' }), settings(), launcher()).includes('--no-trend'));
    assert.ok(!buildArgs(request('commit', { commit: 'a' }), settings(), launcher()).includes('--no-trend'));
  });

  it('asks for the LLM summary only when the run wants one', () => {
    assert.ok(buildArgs(request('workspace'), settings(), launcher()).includes('--no-llm'));
    assert.ok(!buildArgs(request('workspace', { llm: true }), settings(), launcher()).includes('--no-llm'));
  });

  it('asks for HTML only when the run will have a report to show', () => {
    assert.ok(!buildArgs(request('workspace', { html: true }), settings(), launcher()).includes('--no-html'));
    assert.ok(buildArgs(request('file', { relPath: 'a.py' }), settings(), launcher()).includes('--no-html'));
  });

  it('expands a ~ in the config path, which argparse would not', () => {
    const args = buildArgs(request('workspace'), settings({ configPath: '~/x/.gandalf.toml' }), launcher());
    assert.ok(valueAfter(args, '--config')?.startsWith('/'));
    assert.ok(valueAfter(args, '--config')?.endsWith('/x/.gandalf.toml'));
  });

  it('passes a concurrency only when one was chosen', () => {
    assert.ok(!buildArgs(request('workspace'), settings({ concurrency: 0 }), launcher()).includes('--concurrency'));
    assert.equal(
      valueAfter(buildArgs(request('workspace'), settings({ concurrency: 4 }), launcher()), '--concurrency'),
      '4',
    );
  });

  it('repeats --exclude rather than joining, since a path may contain a comma', () => {
    const args = buildArgs(
      request('workspace', { excludes: ['node_modules', 'a,b'] }),
      settings(),
      launcher(),
    );
    assert.equal(args.filter((a) => a === '--exclude').length, 2);
    assert.ok(args.includes('a,b'));
  });

  it('streams only when something is listening and the build can', () => {
    const listening = { onGate: () => undefined };
    assert.ok(buildArgs(request('workspace', listening), settings(), launcher()).includes('--stream'));
    assert.ok(!buildArgs(request('workspace'), settings(), launcher()).includes('--stream'));
  });

  it('withholds the flags it knows an older build may not have', () => {
    // `--help` is how the launcher learns what this build takes. These four are
    // the ones it gates on; `--cache` is deliberately not among them today, and
    // this test records that rather than asserting the behaviour it does not have.
    const old = launcher([]);
    const args = buildArgs(
      request('workspace', { excludes: ['node_modules'], onGate: () => undefined }),
      settings({ concurrency: 4 }),
      old,
    );
    for (const flag of ['--out-dir', '--no-trend', '--stream', '--exclude']) {
      assert.ok(!args.includes(flag), `${flag} was passed to a build that has no such flag`);
    }
    // The flags gandalf has always had are still passed, unconditionally.
    assert.ok(args.includes('--no-llm'));
    assert.ok(args.includes('--concurrency'));
  });

  it('puts the user’s own arguments last, so they win', () => {
    const args = buildArgs(request('workspace'), settings({ extraArgs: ['--fail-under', '80'] }), launcher());
    assert.deepEqual(args.slice(-2), ['--fail-under', '80']);
  });
});
