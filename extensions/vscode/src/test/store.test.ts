/**
 * The store's merge order and its memoization. The memo is the part worth
 * testing hardest: a missed invalidation shows the user a stale board, which is
 * far worse than the work it saves.
 */
import * as assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { normalizeGate } from '../parse';
import { ResultStore } from '../store';
import { Finding, RawGate, Snapshot } from '../types';

const folder = { uri: { fsPath: '/repo', toString: () => 'file:///repo' }, name: 'repo', index: 0 };
const other = { uri: { fsPath: '/two', toString: () => 'file:///two' }, name: 'two', index: 1 };

function gate(name: string, messages: string[]): RawGate {
  return {
    name,
    outcome: 'warn',
    score: 0.5,
    summary: `${name}: ${messages.length}`,
    category: 'Code quality',
    findings: messages.map((m) => ({ message: m })),
  };
}

const findingsOf = (name: string, messages: string[]): Finding[] =>
  normalizeGate(gate(name, messages), '/repo');

function snapshot(gates: RawGate[]): Snapshot {
  const findings = gates.flatMap((g) => normalizeGate(g, '/repo'));
  return {
    payload: {
      gates,
      verdict: 'warn',
      score: 50,
      scope: 'working-tree',
      skipped_gates: [],
      disabled_gates: [],
    },
    findings,
    blocked: [],
    inapplicable: [],
    jsonPath: '',
    htmlPath: '',
    scope: 'working-tree',
    at: Date.now(),
  };
}

const messages = (store: ResultStore, f = folder) =>
  store.findings(f as never)
    .map((x) => `${x.gate}:${x.message}`)
    .sort();

describe('result store', () => {
  it('serves the last project run', () => {
    const store = new ResultStore();
    store.setProject(folder as never, snapshot([gate('ruff', ['a']), gate('mypy', ['b'])]), 1);
    assert.deepEqual(messages(store), ['mypy:b', 'ruff:a']);
  });

  it('lets a streamed gate replace what the last run said about it', () => {
    const store = new ResultStore();
    store.setProject(folder as never, snapshot([gate('ruff', ['old']), gate('mypy', ['keep'])]), 1);
    store.beginStream(folder as never);
    store.pushStream(folder as never, 'ruff', findingsOf('ruff', ['new']));
    assert.deepEqual(messages(store), ['mypy:keep', 'ruff:new'], 'only ruff is superseded');
  });

  it('drops the partials when the stream ends', () => {
    const store = new ResultStore();
    store.setProject(folder as never, snapshot([gate('ruff', ['old'])]), 1);
    store.beginStream(folder as never);
    store.pushStream(folder as never, 'ruff', findingsOf('ruff', ['new']));
    store.endStream(folder as never);
    assert.deepEqual(messages(store), ['ruff:old']);
  });

  it('keeps folders apart', () => {
    const store = new ResultStore();
    store.setProject(folder as never, snapshot([gate('ruff', ['one'])]), 1);
    store.setProject(other as never, snapshot([gate('ruff', ['two'])]), 1);
    assert.deepEqual(messages(store), ['ruff:one']);
    assert.deepEqual(messages(store, other), ['ruff:two']);
  });

  describe('memoization', () => {
    it('does not re-derive the board when nothing changed', () => {
      const store = new ResultStore();
      store.setProject(folder as never, snapshot([gate('ruff', ['a'])]), 1);
      const first = store.findings(folder as never);
      assert.equal(store.findings(folder as never), first, 'same array, not an equal one');
    });

    it('re-derives after every kind of mutation', () => {
      const store = new ResultStore();
      store.setProject(folder as never, snapshot([gate('ruff', ['a'])]), 1);
      let seen = store.findings(folder as never);

      const changes: [string, () => void][] = [
        ['beginStream', () => store.beginStream(folder as never)],
        ['pushStream', () => store.pushStream(folder as never, 'ruff', findingsOf('ruff', ['b']))],
        ['endStream', () => store.endStream(folder as never)],
        ['setFile', () =>
          store.setFile(folder as never, '/repo/app.py', snapshot([gate('ruff', ['c'])]), 1)],
        ['setProject', () => store.setProject(folder as never, snapshot([gate('ruff', ['d'])]), 1)],
        ['clear', () => store.clear()],
      ];
      for (const [name, mutate] of changes) {
        mutate();
        const next = store.findings(folder as never);
        assert.notEqual(next, seen, `${name} must invalidate the memo`);
        seen = next;
      }
    });

    it('invalidates one folder without staling another', () => {
      const store = new ResultStore();
      store.setProject(folder as never, snapshot([gate('ruff', ['one'])]), 1);
      store.setProject(other as never, snapshot([gate('ruff', ['two'])]), 1);
      store.findings(folder as never);
      store.setProject(other as never, snapshot([gate('ruff', ['three'])]), 1);
      assert.deepEqual(messages(store), ['ruff:one'], 'untouched folder still correct');
      assert.deepEqual(messages(store, other), ['ruff:three'], 'changed folder is fresh');
    });

    it('serves the fresh board immediately after a push', () => {
      const store = new ResultStore();
      store.setProject(folder as never, snapshot([gate('ruff', ['old'])]), 1);
      store.findings(folder as never); // warm the memo
      store.beginStream(folder as never);
      store.pushStream(folder as never, 'ruff', findingsOf('ruff', ['new']));
      assert.deepEqual(messages(store), ['ruff:new']);
    });
  });
});
