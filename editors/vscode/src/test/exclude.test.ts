/**
 * Translating the editor's exclusions, and matching them the way gandalf will.
 *
 * The MIRROR table below is the same set of cases as the parametrized test in
 * `tests/test_ignore.py`. Two implementations of one rule is a drift risk, and
 * drift here means the extension silently skips a file gandalf would have
 * scanned — so the table is kept identical on both sides deliberately.
 */
import * as assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { enabledGlobs, excludePatterns, expandBraces, isExcluded, toGandalfPattern } from '../exclude';

const MIRROR: [string, string, boolean][] = [
  ['node_modules/react/index.js', 'node_modules', true],
  ['web/node_modules/react/index.js', 'node_modules', true],
  ['node_modules', 'node_modules', true],
  ['node_modules_old/a.js', 'node_modules', false],
  ['src/node_modulesish.py', 'node_modules', false],
  ['src/generated/api.py', 'src/generated', true],
  ['lib/src/generated/api.py', 'src/generated', false],
  ['web/static/app.min.js', '*.min.js', true],
  ['web/static/app.js', '*.min.js', false],
  ['vendor/jquery/dist/a.js', 'vendor/*', true],
  ['.env', '.env', true],
  ['config/.env', '.env', true],
  ['data/dump.sql', 'data/', true],
  ['./data/dump.sql', 'data', true],
  ['data/dump.sql', './data', true],
  ['src\\generated\\api.py', 'src/generated', true],
  ['src/app.py', '', false],
  ['', 'node_modules', false],
];

describe('exclusion matching', () => {
  for (const [path, pattern, expected] of MIRROR) {
    it(`${JSON.stringify(path)} vs ${JSON.stringify(pattern)} → ${expected}`, () => {
      assert.equal(isExcluded(path, [pattern]), expected);
    });
  }

  it('takes any matching pattern', () => {
    const patterns = ['dist', '*.min.js', 'src/generated'];
    assert.ok(isExcluded('src/generated/x.py', patterns));
    assert.ok(isExcluded('a/dist/b.css', patterns));
    assert.ok(!isExcluded('src/app.py', patterns));
  });

  it('matches a glob against a directory segment, not just the basename', () => {
    assert.ok(isExcluded('a/build_out/x.py', ['build_*']));
  });
});

describe('translating VS Code globs', () => {
  it('drops the depth markers gandalf does not need', () => {
    assert.equal(toGandalfPattern('**/node_modules'), 'node_modules');
    assert.equal(toGandalfPattern('**/node_modules/**'), 'node_modules');
    assert.equal(toGandalfPattern('node_modules/**'), 'node_modules');
    assert.equal(toGandalfPattern('**/*.min.js'), '*.min.js');
    assert.equal(toGandalfPattern('**/.git/objects/**'), '.git/objects');
    assert.equal(toGandalfPattern('.git'), '.git');
  });

  it('refuses a pattern that would exclude everything', () => {
    assert.equal(toGandalfPattern('**'), '');
    assert.equal(toGandalfPattern('*'), '');
    assert.equal(toGandalfPattern('  '), '');
  });

  it('expands the brace alternation gandalf cannot read', () => {
    assert.deepEqual(expandBraces('**/*.{js,map}'), ['**/*.js', '**/*.map']);
    assert.deepEqual(expandBraces('{a,b}/{c,d}'), ['a/c', 'a/d', 'b/c', 'b/d']);
    assert.deepEqual(expandBraces('plain'), ['plain']);
    // Nested braces are left whole rather than half-expanded into a wrong glob.
    assert.deepEqual(expandBraces('{a,{b,c}}'), ['{a,{b,c}}']);
  });

  it('takes only the unconditionally-enabled entries of an exclude map', () => {
    assert.deepEqual(
      enabledGlobs({
        '**/node_modules': true,
        '**/.git': true,
        '**/dist': false,
        '**/*.js': { when: '$(basename).ts' },
      }),
      ['**/node_modules', '**/.git'],
    );
    assert.deepEqual(enabledGlobs(undefined), []);
    assert.deepEqual(enabledGlobs('nonsense'), []);
  });

  it('merges the sources, translated and deduped', () => {
    assert.deepEqual(
      excludePatterns(['vendor'], ['**/node_modules', '**/dist/**'], ['**/node_modules', '**']),
      ['vendor', 'node_modules', 'dist'],
    );
  });

  it("turns VS Code's real defaults into patterns that match", () => {
    const patterns = excludePatterns(
      undefined,
      enabledGlobs({ '**/.git': true, '**/.DS_Store': true, '**/node_modules': true }),
    );
    assert.deepEqual(patterns, ['.git', '.DS_Store', 'node_modules']);
    assert.ok(isExcluded('web/node_modules/left-pad/index.js', patterns));
    assert.ok(isExcluded('.git/config', patterns));
    assert.ok(!isExcluded('src/app.py', patterns));
  });
});
