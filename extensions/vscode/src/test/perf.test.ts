/**
 * Performance, asserted as *work done* rather than as elapsed time.
 *
 * A wall-clock threshold on a shared CI runner is either so loose it catches
 * nothing or so tight it fails on a noisy neighbour, and either way it tells
 * you a number instead of a cause. Every hot path here has a countable
 * invariant behind it instead — how many times the board is walked, how many
 * paths are resolved, how many writes cross to the renderer — and those hold
 * on any machine, at any load, at any tree size.
 *
 * The one exception is the last test, which is a complexity tripwire: a bound
 * with ~100x headroom, there to catch an accidental O(n²), not to measure one.
 *
 * Run with `npm test`.
 */
import * as assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { after, before, describe, it } from 'node:test';

import { DiagnosticPublisher } from '../diagnostics';
import { FindingsView } from '../findingsView';
import { compareFindings, normalize, normalizeGate, pathCache } from '../parse';
import { ResultStore } from '../store';
import { Finding, Payload, RawFinding, RawGate, Snapshot } from '../types';
import { diagnosticCollections, quickPick, workspace } from './vscode-shim';

let root = '';
const folder = { uri: { fsPath: '', toString: () => '' }, name: 'repo', index: 0 };

before(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'gandalf-perf-'));
  folder.uri = { fsPath: root, toString: () => `file://${root}` };
  workspace.workspaceFolders = [folder as never];
});

after(() => fs.rmSync(root, { recursive: true, force: true }));

function realFiles(n: number): string[] {
  const made: string[] = [];
  for (let i = 0; i < n; i += 1) {
    const rel = `src/mod${i}/file${i}.py`;
    fs.mkdirSync(path.join(root, path.dirname(rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), 'x = 1\n');
    made.push(rel);
  }
  return made;
}

function gate(name: string, findings: RawFinding[]): RawGate {
  return {
    name,
    outcome: 'warn',
    score: 0.5,
    summary: `${name}: ${findings.length}`,
    findings,
    category: 'Code quality',
  };
}

function payloadOf(gates: RawGate[]): Payload {
  return {
    scope: 'working-tree',
    verdict: 'warn',
    score: 50,
    skipped_gates: [],
    disabled_gates: [],
    gates,
  };
}

function snapshotOf(findings: Finding[], gates: RawGate[]): Snapshot {
  return {
    payload: payloadOf(gates),
    findings,
    blocked: [],
    inapplicable: [],
    jsonPath: '',
    htmlPath: '',
    scope: 'working-tree',
    at: 0,
  };
}

/** A path cache that records how many resolutions actually hit the disk. */
class CountingCache extends Map<string, string> {
  resolutions = 0;
  override set(key: string, value: string): this {
    this.resolutions += 1;
    return super.set(key, value);
  }
}

/** A store that records how many times something asked it for the whole board. */
class CountingStore extends ResultStore {
  walks = 0;
  override findings(f: never): Finding[] {
    this.walks += 1;
    return super.findings(f);
  }
}

describe('performance invariants', () => {
  describe('normalizing', () => {
    it('resolves each distinct path once, not once per finding', () => {
      const files = realFiles(20);
      // 20 files, 10 findings each: 200 findings over 20 distinct paths.
      const gates = files.map((rel, i) =>
        gate(
          `gate${i}`,
          Array.from({ length: 10 }, (_, k) => ({ path: rel, line: k + 1, message: `m${k}` })),
        ),
      );
      const cache = new CountingCache();
      const findings = normalize(payloadOf(gates), root, cache);

      assert.equal(findings.length, 200);
      assert.equal(cache.resolutions, files.length, 'one filesystem resolution per distinct path');
    });

    it('shares the cache across gates, which is how a streamed run normalizes', () => {
      const [rel] = realFiles(1);
      const cache = new CountingCache();
      // Streaming hands gates over one at a time; a fresh cache per gate would
      // re-stat paths an earlier gate already resolved.
      for (const name of ['ruff', 'mypy', 'semgrep']) {
        normalizeGate(gate(name, [{ path: rel, line: 1, message: 'x' }]), root, cache);
      }
      assert.equal(cache.resolutions, 1, 'the second and third gate hit the cache');
    });

    it('places an unresolvable path once too, instead of re-statting it', () => {
      const cache = new CountingCache();
      const findings = Array.from({ length: 50 }, () => ({ path: 'gone/missing.py', message: 'x' }));
      normalizeGate(gate('ghost', findings), root, cache);
      assert.equal(cache.resolutions, 1, 'a miss is cached as hard as a hit');
    });
  });

  describe('the findings pane', () => {
    /** Wire a pane up to a store holding `count` findings and paint it once. */
    function paneOver(count: number): { view: FindingsView; store: CountingStore } {
      const files = realFiles(count);
      const g = gate(
        'ruff',
        files.map((rel, i) => ({ path: rel, line: i + 1, message: `finding ${i}`, severity: 'high' })),
      );
      const findings = normalizeGate(g, root, pathCache());
      const store = new CountingStore();
      store.setProject(folder as never, snapshotOf(findings, [g]), 1);
      const view = new FindingsView(store);
      view.register();
      store.walks = 0; // Count only what the repaint under test does.
      return { view, store };
    }

    it('walks the board once per repaint, not once per thing that reads it', () => {
      const { view, store } = paneOver(12);
      view.refresh();
      // The chrome and the tree are two readers of one list — three when the
      // filter hides everything and the message has to count what it hid. Each
      // used to ask the store for the board and re-filter it from scratch.
      view.getChildren();

      assert.equal(store.walks, 1, `one walk per repaint, saw ${store.walks}`);
      view.dispose();
    });

    it('walks it again after a refresh, so the pane is never stale', () => {
      const { view, store } = paneOver(6);
      view.refresh();
      view.getChildren();
      const afterFirst = store.walks;

      view.refresh();
      view.getChildren();
      assert.ok(store.walks > afterFirst, 'a refresh must re-read, memo or no memo');
      view.dispose();
    });

    it('counts every level and severity in a single pass', async () => {
      const { view } = paneOver(4);
      quickPick.answer = undefined; // Cancel the picker; the tallies are the point.
      await view.pickFilters();

      const items = quickPick.lastItems as { label: string; description?: string }[];
      const high = items.find((i) => i.label === 'High');
      const errors = items.find((i) => i.label === 'Errors');
      assert.equal(high?.description, '4', 'every finding is HIGH');
      assert.equal(errors?.description, '4', 'and HIGH squiggles as an error');
      view.dispose();
    });
  });

  describe('diagnostics', () => {
    it('writes the collection once, however many files have findings', () => {
      const files = realFiles(30);
      const g = gate(
        'ruff',
        files.map((rel) => ({ path: rel, line: 1, message: 'x', severity: 'high' })),
      );
      const findings = normalizeGate(g, root, pathCache());

      const publisher = new DiagnosticPublisher();
      const collection = diagnosticCollections[diagnosticCollections.length - 1];
      publisher.publish([
        {
          findings,
          settings: { diagnosticsEnabled: true, minSeverity: 'info' } as never,
        },
      ]);

      assert.equal(collection.entries.size, files.length, 'every file got its diagnostics');
      assert.equal(collection.setCalls, 1, `one bulk write, saw ${collection.setCalls}`);
      publisher.dispose();
    });
  });

  /**
   * The tripwire. Everything above pins a constant; this pins the *shape* of
   * the curve. 20k findings is roughly a first scan of a large untended repo,
   * and the pipeline below is what a repaint costs at that size — tens of
   * milliseconds when the sort and the merge are O(n log n), minutes if either
   * ever becomes quadratic. The bound is deliberately absurd so that a slow,
   * loaded or cold CI runner can never trip it on its own.
   */
  describe('complexity tripwire', () => {
    it('normalizes, merges and sorts 20k findings well inside a loose bound', { timeout: 15_000 }, () => {
      const gates = Array.from({ length: 40 }, (_, g) =>
        gate(
          `gate${g}`,
          Array.from({ length: 500 }, (_, i) => ({
            path: `src/mod${i % 200}/file${i % 200}.py`,
            line: (i % 400) + 1,
            message: `finding ${g}-${i}`,
            severity: ['critical', 'high', 'medium', 'low', 'info'][i % 5],
          })),
        ),
      );

      const findings = normalize(payloadOf(gates), root, pathCache());
      assert.equal(findings.length, 20_000);

      const store = new ResultStore();
      store.setProject(folder as never, snapshotOf(findings, gates), 1);
      // A streamed run re-merges and re-sorts the whole board on every gate.
      store.beginStream(folder as never);
      for (const g of gates) {
        store.pushStream(folder as never, g.name, normalizeGate(g, root, pathCache()));
        store.findings(folder as never);
      }
      assert.equal(store.findings(folder as never).length, 20_000);
      // And the comparator itself, run over the whole board once more.
      assert.equal([...findings].sort(compareFindings).length, 20_000);
    });
  });
});
