/** Translating the editor's exclusions into gandalf's dialect. */
import * as assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { enabledGlobs, excludePatterns, expandBraces, toGandalfPattern } from '../exclude';

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

  it("turns VS Code's real defaults into gandalf patterns", () => {
    assert.deepEqual(
      excludePatterns(
        undefined,
        enabledGlobs({ '**/.git': true, '**/.DS_Store': true, '**/node_modules': true }),
      ),
      ['.git', '.DS_Store', 'node_modules'],
    );
  });
});
