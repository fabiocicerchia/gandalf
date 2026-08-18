/**
 * The progress parser, fed the bytes `gandalf/progress.py` actually writes.
 *
 * `REAL` below is a verbatim capture of a run's stderr (GANDALF_PROGRESS=1,
 * stdout redirected): five gates, three stages, `\r`-separated redraws with no
 * trailing newlines.
 */
import * as assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { describeProgress, ProgressParser, shortProgress } from '../progress';

const E = '';
const BAR = (fill: number) => '█'.repeat(fill) + '░'.repeat(20 - fill);
const draw = (body: string) => `\r${E}[K${E}[36m${body}`;
const stage = (i: number, n: number, label: string) => draw(`[${i}/${n}]${E}[0m ${label}`);
const gates = (done: number, total: number, gate: string) =>
  stage(2, 3, `Running ${total} gates  [${BAR(Math.round((20 * done) / total))}] ${done}/${total} ${gate}`);

const REAL =
  stage(1, 3, 'Resolving scope') +
  stage(2, 3, 'Running 5 gates') +
  gates(1, 5, 'build') +
  gates(2, 5, 'vulture') +
  gates(3, 5, 'format') +
  gates(4, 5, 'ruff') +
  gates(5, 5, 'mypy') +
  stage(3, 3, 'Writing reports') +
  '\n';

describe('progress parsing', () => {
  it('reads stage, gate counts and the gate name from a real run', () => {
    const parser = new ProgressParser();
    const seen: string[] = [];
    // One byte at a time: chunk boundaries must not matter.
    for (const ch of REAL) {
      const { progress } = parser.feed(ch);
      if (progress) seen.push(`${progress.stage}|${progress.gatesDone}/${progress.gatesTotal}|${progress.gate}`);
    }
    assert.deepEqual(seen, [
      'Resolving scope|0/0|',
      'Running 5 gates|0/0|',
      'Running 5 gates|1/5|build',
      'Running 5 gates|2/5|vulture',
      'Running 5 gates|3/5|format',
      'Running 5 gates|4/5|ruff',
      'Running 5 gates|5/5|mypy',
      'Writing reports|0/0|',
    ]);
  });

  it('reads a redraw once the next one delimits it', () => {
    const parser = new ProgressParser();
    // A redraw carries no terminator of its own, so it surfaces when the
    // following `\r` arrives — never as a half-written line.
    assert.equal(parser.feed(gates(3, 5, 'format')).progress, undefined);
    const { progress } = parser.feed(gates(4, 5, 'ruff'));
    assert.equal(progress?.gatesDone, 3);
    assert.equal(progress?.gate, 'format');
  });

  it('does not re-report an unchanged state', () => {
    const parser = new ProgressParser();
    parser.feed(gates(2, 5, 'ruff'));
    assert.ok(parser.feed(gates(2, 5, 'ruff')).progress); // Delimits the first.
    assert.equal(parser.feed(gates(2, 5, 'ruff')).progress, undefined);
  });

  it('fills the gate stage proportionally', () => {
    const parser = new ProgressParser();
    parser.feed(gates(2, 5, 'ruff'));
    // Stage 2 of 3 → the first third is done; 2 of 5 gates fills 40% of the second.
    const { progress } = parser.feed(gates(3, 5, 'format'));
    assert.equal(Math.round(progress?.percent ?? 0), 47);
  });

  it('advances monotonically through a whole run', () => {
    const parser = new ProgressParser();
    let last = -1;
    for (const ch of REAL) {
      const { progress } = parser.feed(ch);
      if (!progress) continue;
      assert.ok(progress.percent >= last, `percent went backwards at ${describeProgress(progress)}`);
      last = progress.percent;
    }
  });

  it('hands back real stderr as noise, not progress', () => {
    const parser = new ProgressParser();
    const { progress, noise } = parser.feed(
      `${stage(2, 3, 'Running 5 gates')}\nTraceback (most recent call last):\n  RuntimeError: boom\n`,
    );
    assert.equal(progress?.stage, 'Running 5 gates');
    assert.equal(noise, 'Traceback (most recent call last):\n  RuntimeError: boom\n');
  });

  it('keeps a partial line out of the noise until it is terminated', () => {
    const parser = new ProgressParser();
    assert.equal(parser.feed('gandalf: ignoring config').noise, '');
    assert.equal(parser.feed(' /x/.gandalf.toml\n').noise, 'gandalf: ignoring config /x/.gandalf.toml\n');
  });

  it('flushes an unterminated trailing message when the process exits', () => {
    const parser = new ProgressParser();
    parser.feed('--path src/x.py: no git-tracked files under this folder');
    assert.match(parser.flush(), /no git-tracked files/);
  });

  it('does not flush a progress line as noise', () => {
    const parser = new ProgressParser();
    parser.feed(gates(5, 5, 'mypy'));
    assert.equal(parser.flush(), '');
  });

  it('describes progress for humans', () => {
    const parser = new ProgressParser();
    parser.feed(gates(4, 5, 'ruff'));
    const inGates = parser.feed(gates(5, 5, 'mypy')).progress!;
    assert.equal(describeProgress(inGates), 'gates 4/5 · ruff');
    assert.equal(shortProgress(inGates), '4/5');

    parser.feed(stage(3, 3, 'Writing reports'));
    const inStage = parser.feed('\n').progress!;
    assert.equal(describeProgress(inStage), 'Writing reports');
    assert.equal(shortProgress(inStage), '67%');
  });
});
