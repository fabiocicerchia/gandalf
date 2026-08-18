/** Reading `.gandalf-trend.jsonl` and `git log`, and drawing the result. */
import * as assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { delta, parseLog, parseTrend, sparkline } from '../history';

describe('trend log', () => {
  const LOG = [
    '{"commit": "abc1234", "score": 71, "generated_at": "2026-08-01 10:00:00 UTC"}',
    '{"commit": "def5678", "score": 78, "generated_at": "2026-08-02 10:00:00 UTC"}',
  ].join('\n');

  it('reads a commit, a score and a timestamp per line', () => {
    const trend = parseTrend(LOG + '\n');
    assert.equal(trend.size, 2);
    assert.deepEqual(trend.get('abc1234'), {
      commit: 'abc1234',
      score: 71,
      at: '2026-08-01 10:00:00 UTC',
    });
  });

  it('takes the newest line for a commit scanned more than once', () => {
    const trend = parseTrend(`${LOG}\n{"commit": "abc1234", "score": 95, "generated_at": "later"}\n`);
    assert.equal(trend.get('abc1234')?.score, 95);
  });

  it('survives the torn last line of an append-only log', () => {
    const trend = parseTrend(`${LOG}\n{"commit": "aaa111", "sco`);
    assert.equal(trend.size, 2);
  });

  it('ignores lines that are not scores', () => {
    assert.equal(parseTrend('\n\nnot json\n{"commit": "x"}\n{"score": 5}\n').size, 0);
  });
});

describe('git log', () => {
  it('reads the unit-separated format', () => {
    const commits = parseLog(
      'abc1234\x1ffix: the thing\x1f2026-08-01\ndef5678\x1ffeat: another\x1f2026-08-02\n',
    );
    assert.deepEqual(commits, [
      { short: 'abc1234', subject: 'fix: the thing', date: '2026-08-01' },
      { short: 'def5678', subject: 'feat: another', date: '2026-08-02' },
    ]);
  });

  it('drops anything that is not three fields', () => {
    assert.deepEqual(parseLog('\nbroken line\n\x1f\x1f\n'), []);
  });
});

describe('drawing a history', () => {
  it('scales across the observed range, not 0-100', () => {
    // A repository sitting in the eighties still has visible movement.
    assert.equal(sparkline([80, 85, 90]), '▁▅█');
  });

  it('draws a flat history flat', () => {
    assert.equal(sparkline([80, 80, 80]), '▁▁▁');
  });

  it('handles one point and none', () => {
    assert.equal(sparkline([42]), '▁');
    assert.equal(sparkline([]), '');
  });

  it('signs the change against the previous score', () => {
    assert.equal(delta(78, 71), '+7');
    assert.equal(delta(71, 78), '-7');
    assert.equal(delta(71, 71), '±0');
    assert.equal(delta(71, undefined), '');
  });
});
