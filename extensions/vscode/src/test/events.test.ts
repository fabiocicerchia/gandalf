/**
 * The `--stream` NDJSON reader. Fixtures are lines gandalf actually emits — see
 * `_GateStream` in `gandalf/__main__.py`.
 */
import * as assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { EventParser, GateEvent } from '../events';

const START = '{"event": "start", "scope": "working-tree", "gates": 3}';
const GATE =
  '{"event": "gate", "index": 1, "total": 3, "name": "ruff", "outcome": "warn", "score": 0.7, ' +
  '"summary": "ruff: 1 finding(s)", "findings": [{"filename": "app.py", "code": "E501", ' +
  '"message": "line too long", "location": {"row": 3, "column": 1}}], "category": "Code quality", ' +
  '"duration": 0.42, "blocking": false}';

describe('stream events', () => {
  it('reads a start event', () => {
    const [e] = new EventParser().feed(START + '\n').events;
    assert.deepEqual(e, { event: 'start', scope: 'working-tree', gates: 3 });
  });

  it('reads a gate event with its findings intact', () => {
    const [e] = new EventParser().feed(GATE + '\n').events;
    assert.equal(e.event, 'gate');
    const g = e as GateEvent;
    assert.equal(g.name, 'ruff');
    assert.equal(g.outcome, 'warn');
    assert.equal(g.index, 1);
    assert.equal(g.category, 'Code quality');
    assert.equal(g.duration, 0.42);
    assert.equal(g.findings.length, 1);
    assert.equal(g.findings[0].code, 'E501');
  });

  it('does not mind how chunks are split', () => {
    const parser = new EventParser();
    const stream = `${START}\n${GATE}\n`;
    const events = [];
    for (const ch of stream) events.push(...parser.feed(ch).events);
    assert.deepEqual(
      events.map((e) => e.event),
      ['start', 'gate'],
    );
  });

  it('separates the scorecard sharing the stream from the events', () => {
    const parser = new EventParser();
    const { events, text } = parser.feed(
      `${GATE}\n\n🧙  GANDALF — working-tree\n  🟡 ruff  1 finding(s)\nJSON report: /tmp/x.json\n`,
    );
    assert.equal(events.length, 1);
    // The caller keeps only this, so the report paths must survive in it.
    assert.match(text, /^JSON report: \/tmp\/x\.json$/m);
    assert.match(text, /GANDALF/);
    assert.doesNotMatch(text, /"event"/, 'the findings themselves are not buffered');
  });

  it('holds a partial line until the newline arrives', () => {
    const parser = new EventParser();
    const half = GATE.slice(0, 40);
    assert.deepEqual(parser.feed(half).events, []);
    assert.equal(parser.feed(GATE.slice(40) + '\n').events.length, 1);
  });

  it('drops a malformed or truncated event rather than throwing', () => {
    const parser = new EventParser();
    assert.deepEqual(parser.feed('{"event": "gate", "name": "ru\n').events, []);
    assert.deepEqual(parser.feed('{"event": "gate", "name": 42, "outcome": "warn"}\n').events, []);
    assert.deepEqual(parser.feed('{"event": "gate", "name": "x", "outcome": "sideways"}\n').events, []);
    assert.deepEqual(parser.feed('{"event": "surprise"}\n').events, []);
    // …and still reads the next good line.
    assert.equal(parser.feed(GATE + '\n').events.length, 1);
  });

  it('defaults the optional fields of a minimal gate event', () => {
    const [e] = new EventParser().feed('{"event": "gate", "name": "x", "outcome": "pass"}\n').events;
    const g = e as GateEvent;
    assert.deepEqual(g.findings, []);
    assert.equal(g.score, 0);
    assert.equal(g.summary, '');
    assert.equal(g.category, undefined);
    assert.equal(g.blocking, false);
  });
});
