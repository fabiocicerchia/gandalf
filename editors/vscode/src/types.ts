/**
 * The shapes gandalf writes to `reports/<stem>.json`, plus the normalized
 * finding the rest of the extension works with.
 *
 * Gate findings are deliberately untyped on the gandalf side: every gate passes
 * through whatever its underlying tool emitted (ruff's `filename`/`location.row`,
 * semgrep's `path`/`start.line`, trivy's `PkgName`, a bare `{finding: "..."}`
 * line, …). `normalize()` in parse.ts is the single place that reconciles them.
 */

export type Outcome = 'pass' | 'warn' | 'fail';
/** Editor severity — what a squiggle can be. */
export type Severity = 'error' | 'warning' | 'info';
/**
 * The severity the *tool* reported, on the ladder they all roughly share.
 * `unrated` is not a gap in the data: plenty of gates publish findings with no
 * severity at all (mypy, vulture, the format gate), and pretending those sit
 * somewhere on the ladder would invent precision. They are filterable as their
 * own bucket, and sort by the gate outcome they inherited.
 */
export type Level = 'critical' | 'high' | 'medium' | 'low' | 'info' | 'unrated';

export interface RawFinding {
  [key: string]: unknown;
}

export interface RawGate {
  name: string;
  outcome: Outcome;
  score: number;
  summary: string;
  findings: RawFinding[];
  /** Gate category ("Security", "Code quality", …) — the report's grouping. */
  category?: string;
  blocking?: boolean;
  duration?: number | null;
}

/**
 * The parts of gandalf's run record the extension reads. Not the whole shape —
 * that is documented in docs/reports.md, and copying it here would mean
 * maintaining a second description of someone else's JSON.
 */
export interface Payload {
  scope: string;
  verdict: Outcome;
  score: number;
  skipped_gates: string[];
  disabled_gates: string[];
  gates: RawGate[];
}

export interface Finding {
  /** Stable across runs: used to dedupe and to address a row from the webview. */
  id: string;
  gate: string;
  category: string;
  /** The gate's own RAG outcome — a finding inherits it when it has no severity. */
  outcome: Outcome;
  severity: Severity;
  /** The tool's own severity word ("HIGH", "MEDIUM", …), when it published one. */
  severityLabel: string;
  /** `severityLabel` placed on the shared ladder, or `unrated` if there wasn't one. */
  level: Level;
  rule: string;
  message: string;
  /** Path exactly as the tool reported it (may be absolute, or container-relative). */
  file: string;
  /** Absolute on-disk path, once we managed to map `file` into the workspace. */
  resolvedPath: string;
  line: number;
  column: number;
  /** Rule documentation, when the tool ships one (ruff does). */
  url: string;
}

/** One completed gandalf run against one workspace folder. */
export interface Snapshot {
  /**
   * The run record, minus each gate's raw `findings` array: those are dropped
   * once normalized, since nothing reads them again and they are most of the
   * payload's weight. Everything derived from them is on this object already.
   */
  payload: Payload;
  findings: Finding[];
  /** Gates that wanted to run and couldn't — computed before the raw data went. */
  blocked: string[];
  /** Gates that had nothing to assess. */
  inapplicable: string[];
  jsonPath: string;
  htmlPath: string;
  /** Scope label as gandalf resolved it ("working-tree", "staged", "…:src/x.py"). */
  scope: string;
  at: number;
}
