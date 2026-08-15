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
export type Severity = 'error' | 'warning' | 'info';

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

export interface Payload {
  scope: string;
  generated_at: string;
  commit: { sha?: string; short?: string; subject?: string; date?: string };
  languages: string[];
  verdict: Outcome;
  passed: boolean;
  policy: { fail_on: string; min_score: number; reason: string };
  score: number;
  summary: string;
  changeset: string;
  remediation: string;
  improvement: string;
  skipped_gates: string[];
  disabled_gates: string[];
  fixes: { gate: string; changed: boolean; message: string }[];
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
  payload: Payload;
  findings: Finding[];
  jsonPath: string;
  htmlPath: string;
  /** Scope label as gandalf resolved it ("working-tree", "staged", "…:src/x.py"). */
  scope: string;
  at: number;
}
