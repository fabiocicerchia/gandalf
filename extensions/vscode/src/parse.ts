/**
 * Turn a gandalf JSON payload into `Finding`s the editor can place.
 *
 * The key lists mirror `gandalf/report.py`, `gandalf/sarif.py` and
 * `gandalf/suppress.py` — the same "first truthy key wins" reconciliation, plus
 * the nested shapes (`location.row`, `start.line`) that only SARIF handled and
 * a last-resort `path:line:` scrape for gates that emit raw tool lines.
 */
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

import { Finding, Level, Outcome, Payload, RawFinding, RawGate, Severity } from './types';

/**
 * What gandalf says about a finding once it has reconciled it — the `_gandalf`
 * block it puts on every finding in the JSON report and every `--stream` event.
 * See `gandalf/findings.py`.
 */
interface Normalised {
  /** Repo-relative, or '' when the finding names no file. */
  path: string;
  /** 1-based; 0 means unknown. */
  line: number;
  column: number;
  rule: string;
  message: string;
  /** '' when the tool published none — not the same as 'unknown', where it published one and declined to rate. */
  severity: string;
  url: string;
}

/**
 * A gandalf older than `findings.py` sends no `_gandalf` block, and pointing
 * `gandalf.path` at an arbitrary checkout makes that a real case. Such a build
 * still has to produce a usable pane, so these are the keys gandalf's own
 * report has always read — deliberately not the full reconciliation, which is
 * no longer this file's job to carry.
 */
const LEGACY_PATH_KEYS = ['path', 'filename', 'file', 'file_path'];
const LEGACY_LINE_KEYS = ['line', 'line_number', 'Line'];
const LEGACY_RULE_KEYS = ['rule_id', 'check_id', 'RuleID', 'test_id', 'code', 'id', 'rule'];
const LEGACY_MESSAGE_KEYS = ['message', 'issue_text', 'description', 'Description', 'error', 'finding'];
const LEGACY_SEVERITY_KEYS = ['severity', 'Severity', 'issue_severity', 'level', 'Level'];
const URL_KEYS = ['url', 'URL', 'PrimaryURL', 'help_uri'];

const OUTCOME_SEVERITY: Record<Outcome, Severity> = {
  fail: 'error',
  warn: 'warning',
  pass: 'info',
};

/**
 * Tool severity word → the shared ladder. Same vocabulary sarif.py maps, plus
 * CRITICAL, which SARIF folds into `error` but which is worth keeping apart when
 * a human is deciding what to look at first. The editor severity is derived
 * from the level below rather than listed again — one table cannot disagree
 * with itself.
 */
/**
 * gandalf's normalized severity → the ladder the pane shows. `unknown` is the
 * tool saying it declined to rate the finding, which is exactly what `unrated`
 * means here; `''` (no severity field at all) lands there too, and inherits the
 * gate's outcome instead.
 */
const GANDALF_LEVEL: Record<string, Level> = {
  critical: 'critical',
  high: 'high',
  medium: 'medium',
  low: 'low',
  info: 'info',
  unknown: 'unrated',
};

/** Worst first — the pane's ordering and the filter's ordering. */
export const LEVELS: Level[] = ['critical', 'high', 'medium', 'low', 'info', 'unrated'];
export const LEVEL_RANK: Record<Level, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
  unrated: 5,
};
export const LEVEL_LABEL: Record<Level, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
  unrated: 'Unrated',
};

export const SEVERITIES: Severity[] = ['error', 'warning', 'info'];
export const SEVERITY_RANK: Record<Severity, number> = { error: 0, warning: 1, info: 2 };
/** The scorecard's own vocabulary for an outcome. */
export const VERDICT_WORD: Record<Outcome, string> = { pass: 'GREEN', warn: 'AMBER', fail: 'RED' };
export const SEVERITY_LABEL: Record<Severity, string> = {
  error: 'Errors',
  warning: 'Warnings',
  info: 'Info',
};

/**
 * Where an unrated finding sorts. Its gate's outcome is the only signal there
 * is, and a failing gate's finding belongs above a tool's LOW — a red mypy
 * error must not sink below a cosmetic advisory just because mypy names no
 * severity.
 */
const IMPLIED_LEVEL: Record<Severity, Level> = {
  error: 'high',
  warning: 'medium',
  info: 'info',
};

/** Level → what it squiggles as. `unrated` has no level to map, so it is absent. */
const LEVEL_SEVERITY: Record<Exclude<Level, 'unrated'>, Severity> = {
  critical: 'error',
  high: 'error',
  medium: 'warning',
  low: 'info',
  info: 'info',
};

export function sortLevel(f: Finding): Level {
  return f.level === 'unrated' ? IMPLIED_LEVEL[f.severity] : f.level;
}

function firstString(f: RawFinding, keys: string[]): string {
  for (const k of keys) {
    const v = f[k];
    if (typeof v === 'string' && v.trim()) return v.trim();
    if (typeof v === 'number' && Number.isFinite(v)) return String(v);
  }
  return '';
}

function firstNumber(f: RawFinding, keys: string[]): number {
  for (const k of keys) {
    const v = f[k];
    if (typeof v === 'number' && Number.isInteger(v) && v > 0) return v;
    if (typeof v === 'string' && /^\d+$/.test(v) && Number(v) > 0) return Number(v);
  }
  return 0;
}

/** The `_gandalf` block, if this build of gandalf emits one. */
function normalised(f: RawFinding): Normalised | undefined {
  const raw = f._gandalf;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined;
  const o = raw as Record<string, unknown>;
  const str = (k: string) => (typeof o[k] === 'string' ? (o[k] as string) : '');
  const num = (k: string) => (typeof o[k] === 'number' && o[k] > 0 ? (o[k] as number) : 0);
  return {
    path: str('path'),
    line: num('line'),
    column: num('column'),
    rule: str('rule'),
    message: str('message'),
    severity: str('severity'),
    url: str('url'),
  };
}

/** Best effort for a gandalf that predates `findings.py`. */
function legacy(f: RawFinding): Normalised {
  return {
    path: firstString(f, LEGACY_PATH_KEYS),
    line: firstNumber(f, LEGACY_LINE_KEYS),
    column: 0,
    rule: firstString(f, LEGACY_RULE_KEYS),
    message: firstString(f, LEGACY_MESSAGE_KEYS),
    severity: firstString(f, LEGACY_SEVERITY_KEYS).toLowerCase(),
    url: firstString(f, URL_KEYS),
  };
}

export function readFinding(f: RawFinding): Normalised {
  return normalised(f) ?? legacy(f);
}

/**
 * Map a tool-reported path onto disk. Tools run either on the host (paths
 * relative to the worktree) or inside the tools image, which mounts the repo at
 * `/src` — so an absolute `/src/...` has to be rebased before it means anything.
 */
export function resolvePath(raw: string, root: string, cache?: Map<string, string>): string {
  if (!raw) return '';
  const key = `${root}\0${raw}`;
  const hit = cache?.get(key);
  if (hit !== undefined) return hit;

  const cleaned = raw.replace(/\\/g, '/').replace(/^\.\//, '');
  const candidates: string[] = [];
  if (path.isAbsolute(cleaned)) {
    candidates.push(cleaned);
    // The container mounts the worktree at /src, and gandalf's own scopes use
    // a temporary worktree — both leave an absolute prefix we have to shed.
    const marker = cleaned.indexOf('/src/');
    if (cleaned.startsWith('/src/')) candidates.push(path.join(root, cleaned.slice(5)));
    else if (marker > 0) candidates.push(path.join(root, cleaned.slice(marker + 5)));
    if (cleaned.startsWith(root)) candidates.push(cleaned);
  } else {
    candidates.push(path.join(root, cleaned));
  }

  let resolved = '';
  for (const c of candidates) {
    try {
      if (fs.statSync(c).isFile()) {
        resolved = c;
        break;
      }
    } catch {
      // Not on disk under this interpretation — try the next one.
    }
  }
  cache?.set(key, resolved);
  return resolved;
}

/**
 * gandalf reports a repo-relative path; the editor needs an absolute one that
 * exists. A finding whose file cannot be found is still listed in the pane —
 * it just gets no squiggle.
 */
function place(n: Normalised, root: string, cache: Map<string, string>) {
  return { file: n.path, resolvedPath: n.path ? resolvePath(n.path, root, cache) : '' };
}

/**
 * Editor severity for a finding. A tool that named no severity leaves the level
 * unrated, and the finding inherits its gate's outcome — a red mypy error must
 * not sink below a cosmetic advisory just because mypy names no severity.
 */
function rate(n: Normalised, outcome: Outcome): { severity: Severity; label: string; level: Level } {
  const level = GANDALF_LEVEL[n.severity] ?? 'unrated';
  return {
    severity: level === 'unrated' ? OUTCOME_SEVERITY[outcome] : LEVEL_SEVERITY[level],
    // A level we place on the ladder is worth showing; one we don't isn't.
    label: level === 'unrated' ? '' : n.severity.toUpperCase(),
    level,
  };
}

function fingerprint(parts: (string | number)[]): string {
  return crypto.createHash('sha1').update(parts.join('\0')).digest('hex').slice(0, 16);
}

/** A gate that wanted to run and couldn't — missing tool, timeout, dead judge. */
const BLOCKED = /\bunavailable\b|\bdid not run\b|\btimed out\b|not found|not installed|not verified locally/i;
/** A gate that had nothing to do — no `--target`, no request to judge, … */
const INAPPLICABLE = /\bskipped\b|\bno target\b|no request|nothing in scope|no database/i;

export type GateStatus = 'reported' | 'blocked' | 'inapplicable';

/**
 * Did this gate actually assess anything?
 *
 * gandalf answers "my tool isn't here" with an AMBER gate and a summary, which
 * looks exactly like a real warning. In a bare environment that is thirty-odd
 * rows of noise burying the findings that matter, so they are counted in the
 * panel's notice bar instead of listed. Only ever applied to AMBER gates with
 * no findings — a red gate is always shown, whatever its summary says.
 */
export function gateStatus(gate: RawGate): GateStatus {
  if ((gate.findings?.length ?? 0) > 0 || gate.outcome !== 'warn') return 'reported';
  if (BLOCKED.test(gate.summary)) return 'blocked';
  if (INAPPLICABLE.test(gate.summary)) return 'inapplicable';
  return 'reported';
}

/**
 * Resolving a path means hitting the filesystem, so callers pass a cache. Share
 * one across a whole run: streaming normalizes gate by gate, and without a
 * shared cache every finding re-stats a path a previous gate already resolved —
 * measured at one `statSync` per finding instead of one per distinct file.
 */
export function pathCache(): Map<string, string> {
  return new Map();
}

/**
 * One gate's findings. Public because `--stream` delivers gates one at a time,
 * long before there is a payload to normalize as a whole.
 */
export function normalizeGate(
  gate: RawGate,
  root: string,
  cache: Map<string, string> = pathCache(),
): Finding[] {
  const category = gate.category || 'Other';
  const findings: Finding[] = [];

  for (const raw of gate.findings ?? []) {
    const f: RawFinding = raw && typeof raw === 'object' ? raw : { finding: String(raw) };
    const n = readFinding(f);
    const { severity, label, level } = rate(n, gate.outcome);
    const { file, resolvedPath } = place(n, root, cache);
    // Nothing recognizable at all: show the raw record rather than an empty row.
    const message = n.message || JSON.stringify(f);
    findings.push({
      id: fingerprint([gate.name, file, n.rule, message.slice(0, 200), n.line]),
      gate: gate.name,
      category,
      outcome: gate.outcome,
      severity,
      severityLabel: label,
      level,
      rule: n.rule,
      message: message.slice(0, 2000),
      file,
      resolvedPath,
      line: n.line,
      column: n.column,
      url: n.url,
    });
  }

  // A gate that failed without structured findings still has to be visible —
  // its summary is the whole story (a build error, a failing test suite).
  if (findings.length === 0 && gate.outcome !== 'pass' && gateStatus(gate) === 'reported') {
    findings.push({
      id: fingerprint([gate.name, 'gate-level', gate.summary]),
      gate: gate.name,
      category,
      outcome: gate.outcome,
      severity: OUTCOME_SEVERITY[gate.outcome],
      severityLabel: '',
      level: 'unrated',
      rule: '',
      message: gate.summary || gate.name,
      file: '',
      resolvedPath: '',
      line: 0,
      column: 0,
      url: '',
    });
  }
  return findings;
}

/**
 * Sort: reported level, then gate, then file, then line — the pane's order.
 *
 * ponytail: `localeCompare` looks like the slow way to do this and isn't — V8
 * fast-paths it for the default locale. Hoisting an `Intl.Collator` out of the
 * comparator, which is the usual advice, measured **5x slower** here (33ms vs
 * 6ms sorting 20k paths, `scripts/bench.py`): the extracted `.compare` loses
 * the fast path, and `numeric: true` disables it outright. Leave this alone.
 */
export function compareFindings(a: Finding, b: Finding): number {
  return (
    LEVEL_RANK[sortLevel(a)] - LEVEL_RANK[sortLevel(b)] ||
    SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
    // Tie on effective rank: a level the tool actually stated outranks one
    // inferred from the gate's outcome. Otherwise the gate's name would decide,
    // which is arbitrary.
    Number(a.level === 'unrated') - Number(b.level === 'unrated') ||
    a.gate.localeCompare(b.gate) ||
    a.resolvedPath.localeCompare(b.resolvedPath) ||
    a.line - b.line
  );
}

export function normalize(
  payload: Payload,
  root: string,
  cache: Map<string, string> = pathCache(),
): Finding[] {
  const out: Finding[] = [];
  for (const gate of payload.gates ?? []) out.push(...normalizeGate(gate, root, cache));
  return out.sort(compareFindings);
}

/**
 * Split out the gates that assessed nothing, so "green" never quietly means
 * "never checked": `blocked` is actionable (install the tool, build the image),
 * `inapplicable` is expected (no `--target` in an editor). Names only — this is
 * computed while the payload still has its raw findings, and outlives them.
 */
export function gatesByStatus(payload: Payload): { blocked: string[]; inapplicable: string[] } {
  const blocked: string[] = [];
  const inapplicable: string[] = [];
  for (const gate of payload.gates ?? []) {
    const status = gateStatus(gate);
    if (status === 'blocked') blocked.push(gate.name);
    else if (status === 'inapplicable') inapplicable.push(gate.name);
  }
  return { blocked, inapplicable };
}

/**
 * Drop each gate's raw findings from a payload we are about to retain. They are
 * the bulk of it (measured at 46% of a 10k-finding snapshot) and nothing reads
 * them once `normalize` has run — every consumer works off `Finding`s or the
 * gate's own name/outcome/summary/duration.
 */
export function slim(payload: Payload): Payload {
  for (const gate of payload.gates ?? []) gate.findings = [];
  return payload;
}

/**
 * Gates that recorded a wall-clock, slowest first — the answer to "why does a
 * full scan take so long". A gate that reported no duration is not a zero, so it
 * is left out rather than sorted to the bottom.
 */
export function gatesByDuration(payload: Payload | undefined): RawGate[] {
  return (payload?.gates ?? [])
    .filter((g) => typeof g.duration === 'number')
    .sort((a, b) => (b.duration ?? 0) - (a.duration ?? 0));
}
