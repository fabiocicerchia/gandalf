/**
 * The extension's own hot paths, measured. Driven by `scripts/bench.py`, which
 * merges these rows with gandalf's and draws the chart; run it directly with
 * `node esbuild.mjs --bench && node out/bench.js`.
 *
 * Not a test. The invariants that belong in CI — one walk per repaint, one
 * bulk diagnostic write — are counted in `test/perf.test.ts`, where they hold
 * on any machine. This is here to say how big the numbers actually are.
 *
 * Where the old implementation is still expressible it is kept beside the new
 * one, so a claimed speedup is a measurement rather than a recollection. That
 * cuts both ways: it is how the Intl.Collator "optimization" was caught being
 * five times slower than the localeCompare it was meant to replace.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { compareFindings, normalize, normalizeGate, pathCache } from './parse';
import { ResultStore } from './store';
import { Finding, Payload, RawFinding, RawGate, Snapshot } from './types';
import { workspace } from './test/vscode-shim';

const FINDINGS = 20_000;
const GATES = 40;
const REPEAT = 5;

interface Row {
  id: string;
  label: string;
  unit: string;
  before?: number;
  after: number;
}

/** Milliseconds for the fastest of `repeat` runs — see the note in bench.py. */
function timed(fn: () => unknown, repeat = REPEAT): number {
  let best = Infinity;
  for (let i = 0; i < repeat; i += 1) {
    const started = process.hrtime.bigint();
    fn();
    best = Math.min(best, Number(process.hrtime.bigint() - started) / 1e6);
  }
  return best;
}

function rawGates(): RawGate[] {
  const perGate = FINDINGS / GATES;
  return Array.from({ length: GATES }, (_, g) => ({
    name: `gate${g}`,
    outcome: 'warn' as const,
    score: 0.5,
    summary: `gate${g}: ${perGate} finding(s)`,
    category: 'Code quality',
    findings: Array.from({ length: perGate }, (_, i): RawFinding => ({
      path: `src/pkg${i % 200}/mod${i % 500}.py`,
      line: (i % 400) + 1,
      message: `finding ${g}-${i} — something the tool wants changed`,
      severity: (['HIGH', 'MEDIUM', 'LOW'] as const)[i % 3],
      rule_id: `R${String(i % 90).padStart(3, '0')}`,
      _gandalf: {
        path: `src/pkg${i % 200}/mod${i % 500}.py`,
        line: (i % 400) + 1,
        column: 0,
        rule: `R${String(i % 90).padStart(3, '0')}`,
        message: `finding ${g}-${i} — something the tool wants changed`,
        severity: (['high', 'medium', 'low'] as const)[i % 3],
        url: '',
      },
    })),
  })).map((g) => ({ ...g, findings: g.findings }));
}

function payloadOf(gates: RawGate[]): Payload {
  return {
    scope: 'working-tree',
    verdict: 'warn',
    score: 61,
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

function main(): void {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gandalf-bench-'));
  // A real tree behind the findings, so path resolution does real work.
  for (let i = 0; i < 200; i += 1) {
    const dir = path.join(root, `src/pkg${i}`);
    fs.mkdirSync(dir, { recursive: true });
    for (let k = 0; k < 3; k += 1) fs.writeFileSync(path.join(dir, `mod${i + k}.py`), 'x = 1\n');
  }
  const folder = { uri: { fsPath: root, toString: () => `file://${root}` }, name: 'repo', index: 0 };
  workspace.workspaceFolders = [folder as never];

  const gates = rawGates();
  const findings = normalize(payloadOf(gates), root, pathCache());
  const rows: Row[] = [];

  rows.push({
    id: 'normalize',
    label: `Normalize ${FINDINGS / 1000}k findings`,
    unit: 'ms',
    after: timed(() => normalize(payloadOf(gates), root, pathCache()), 3),
  });

  // Cost only, no A/B: hoisting an Intl.Collator out of the comparator — the
  // usual advice — measured 5x *slower*, and the finding is recorded where
  // someone would go to make the change (see compareFindings in parse.ts).
  rows.push({
    id: 'sort',
    label: `Sort ${FINDINGS / 1000}k findings`,
    unit: 'ms',
    after: timed(() => [...findings].sort(compareFindings)),
  });

  // A streamed run re-merges and re-sorts the board once per gate, so this is
  // what the pane costs over a whole scan, not for one repaint.
  const streamedRun = (): void => {
    const store = new ResultStore();
    store.setProject(folder as never, snapshotOf(findings, gates), 1);
    store.beginStream(folder as never);
    for (const g of gates) {
      store.pushStream(folder as never, g.name, normalizeGate(g, root, pathCache()));
      store.findings(folder as never);
    }
  };
  rows.push({
    id: 'streamed-board',
    label: `Rebuild the board, ${GATES} streamed gates`,
    unit: 'ms',
    after: timed(streamedRun, 3),
  });

  fs.rmSync(root, { recursive: true, force: true });
  process.stdout.write(JSON.stringify(rows, null, 2) + '\n');
}

main();
