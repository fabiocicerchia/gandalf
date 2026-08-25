/**
 * The content guard: it decides whether a save is worth a scan at all, and it
 * is the one map in the extension that used to grow for the life of the window.
 */
import * as assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { describe, it } from 'node:test';

import { ContentGuard } from '../scheduler';

function tempFile(contents: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gandalf-guard-'));
  const file = path.join(dir, 'a.txt');
  fs.writeFileSync(file, contents);
  return file;
}

describe('content guard', () => {
  it('sees a file as changed until a scan commits its hash', async () => {
    const guard = new ContentGuard();
    const file = tempFile('one');

    const first = await guard.inspect(file);
    assert.equal(first.unchanged, false, 'never scanned — must not be skipped');

    guard.commit(file, first.hash);
    assert.equal((await guard.inspect(file)).unchanged, true);

    fs.writeFileSync(file, 'two');
    assert.equal((await guard.inspect(file)).unchanged, false);
  });

  it('reports a missing file as changed rather than throwing', async () => {
    const guard = new ContentGuard();
    assert.deepEqual(await guard.inspect('/no/such/file'), { unchanged: false, hash: '' });
  });

  it('stays bounded — the map used to grow with every file ever saved', () => {
    const guard = new ContentGuard();
    for (let i = 0; i < 10_000; i += 1) guard.commit(`/repo/f${i}.ts`, `hash-${i}`);
    assert.ok(guard.size <= 4096, `expected a bounded map, got ${guard.size}`);
  });
});
