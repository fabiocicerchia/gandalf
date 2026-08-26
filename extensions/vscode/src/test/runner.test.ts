/**
 * Killing a run kills the whole run.
 *
 * gandalf shells out to the scanners, so the process that has to die on a
 * cancel or a timeout is the group, not the python parent — otherwise a
 * cancelled scan leaves a trivy orphaned onto the extension host, still
 * pinning a core minutes later.
 */
import * as assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { describe, it } from 'node:test';

import { probe } from '../runner';

const alive = (pid: number): boolean => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe('probe', { skip: process.platform === 'win32' ? 'POSIX process groups' : false }, () => {
  it('takes the grandchildren down with the child', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gandalf-runner-'));
    const pidFile = path.join(dir, 'pid');

    // A stand-in for `python -m gandalf` spawning trivy: the shell is the child,
    // the sleep is the scanner that used to survive.
    const { ok } = await probe('sh', ['-c', `sleep 60 & echo $! > ${pidFile}; wait`], dir, 500);
    assert.equal(ok, false, 'the timeout should have fired');

    const pid = Number(fs.readFileSync(pidFile, 'utf8').trim());
    assert.ok(pid > 0, 'grandchild pid should have been recorded');
    await sleep(200); // Signal delivery is not instant.
    assert.equal(alive(pid), false, `grandchild ${pid} survived the kill`);

    fs.rmSync(dir, { recursive: true, force: true });
  });
});
