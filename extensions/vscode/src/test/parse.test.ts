/**
 * The normalizer is the one piece that has to understand every gate's output
 * shape, so it gets real fixtures: the exact dicts ruff, semgrep, mypy, kics,
 * trivy and the "raw tool line" gates put in `findings`.
 *
 * Run with `npm test`.
 */
import * as assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { after, before, describe, it } from 'node:test';

import { gatesByStatus, LEVELS, normalize, resolvePath, sortLevel } from '../parse';
import { Payload, RawFinding, RawGate } from '../types';

let root = '';

function gate(name: string, findings: RawFinding[], extra: Partial<RawGate> = {}): RawGate {
  return {
    name,
    outcome: 'warn',
    score: 0.5,
    summary: `${name}: ${findings.length} finding(s)`,
    findings,
    category: 'Code quality',
    ...extra,
  };
}

function payloadOf(...gates: RawGate[]): Payload {
  return {
    scope: 'working-tree',
    verdict: 'warn',
    score: 70,
    skipped_gates: [],
    disabled_gates: [],
    gates,
  };
}

const one = (...gates: RawGate[]) => normalize(payloadOf(...gates), root);

before(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'gandalf-parse-'));
  fs.mkdirSync(path.join(root, 'src', 'gandalf'), { recursive: true });
  fs.writeFileSync(path.join(root, 'src', 'gandalf', '__main__.py'), 'x = 1\n');
  fs.writeFileSync(path.join(root, 'app.py'), 'y = 2\n');
  fs.writeFileSync(path.join(root, 'Dockerfile'), 'FROM scratch\n');
});

after(() => fs.rmSync(root, { recursive: true, force: true }));

describe('path resolution', () => {
  it('resolves a repo-relative path', () => {
    assert.equal(resolvePath('app.py', root), path.join(root, 'app.py'));
  });

  it('strips the ./ prefix', () => {
    assert.equal(resolvePath('./app.py', root), path.join(root, 'app.py'));
  });

  it('rebases the container mount point', () => {
    // Dockerized tools see the worktree at /src.
    assert.equal(resolvePath('/src/app.py', root), path.join(root, 'app.py'));
  });

  it('accepts an absolute path that is already inside the workspace', () => {
    const abs = path.join(root, 'src', 'gandalf', '__main__.py');
    assert.equal(resolvePath(abs, root), abs);
  });

  it('returns empty for a path that is not on disk', () => {
    assert.equal(resolvePath('nope/missing.py', root), '');
    assert.equal(resolvePath('', root), '');
  });
});

/**
 * A finding as gandalf now delivers it: the tool's own keys untouched, plus the
 * `_gandalf` block that `gandalf/findings.py` computed from them. The blocks
 * below are the real output of that module for these exact fixtures — the
 * Python side pins the same cases in `tests/test_findings.py`, so if the two
 * ever disagree, one of them fails.
 */
function norm(raw: RawFinding, block: Record<string, unknown>): RawFinding {
  return {
    ...raw,
    _gandalf: { path: '', line: 0, column: 0, rule: '', message: '', severity: '', url: '', ...block },
  };
}

describe('finding normalization', () => {
  it('reads ruff: nested location.row/column, code and rule url', () => {
    const [f] = one(
      gate('ruff', [
        norm(
          {
            filename: 'app.py',
            code: 'E501',
            message: 'Line too long (100 > 88)',
            location: { row: 12, column: 89 },
            url: 'https://docs.astral.sh/ruff/rules/line-too-long',
          },
          {
            path: 'app.py',
            line: 12,
            column: 89,
            rule: 'E501',
            message: 'Line too long (100 > 88)',
            url: 'https://docs.astral.sh/ruff/rules/line-too-long',
          },
        ),
      ]),
    );
    assert.equal(f.rule, 'E501');
    assert.equal(f.line, 12);
    assert.equal(f.column, 89);
    assert.equal(f.resolvedPath, path.join(root, 'app.py'));
    assert.equal(f.url, 'https://docs.astral.sh/ruff/rules/line-too-long');
    assert.equal(f.severity, 'warning', 'no severity → inherits the gate outcome');
    assert.equal(f.level, 'unrated');
  });

  it('reads semgrep, including the severity it nests under extra', () => {
    const [f] = one(
      gate(
        'semgrep',
        [
          norm(
            { path: 'app.py', line: 3, check_id: 'python.lang.security.eval', message: 'eval() is dangerous', extra: { severity: 'ERROR' } },
            { path: 'app.py', line: 3, rule: 'python.lang.security.eval', message: 'eval() is dangerous', severity: 'high' },
          ),
        ],
        { outcome: 'fail', category: 'Security' },
      ),
    );
    assert.equal(f.severity, 'error');
    assert.equal(f.severityLabel, 'HIGH');
    assert.equal(f.rule, 'python.lang.security.eval');
    assert.equal(f.category, 'Security');
    assert.equal(f.line, 3);
  });

  it('identifies a bandit finding by its test id, not its source snippet', () => {
    // The regression that motivated moving this into gandalf: `code` is the
    // offending source, and it used to win over `test_id` here.
    const [f] = one(
      gate('bandit', [
        norm(
          {
            filename: 'app.py',
            line_number: 42,
            test_id: 'B105',
            issue_text: 'Possible hardcoded password',
            issue_severity: 'HIGH',
            code: '41 def login():\n42     password = "hunter2"\n',
          },
          { path: 'app.py', line: 42, rule: 'B105', message: 'Possible hardcoded password', severity: 'high' },
        ),
      ]),
    );
    assert.equal(f.rule, 'B105');
    assert.ok(!f.rule.includes('\n'), 'never a multi-line source snippet');
    assert.equal(f.level, 'high');
  });

  it('reads kics: a level folded into the message comes back in its own column', () => {
    const [f] = one(
      gate('kics', [
        norm(
          { file: 'Dockerfile', line: 1, message: '[HIGH] Missing user instruction' },
          { path: 'Dockerfile', line: 1, message: 'Missing user instruction', severity: 'high' },
        ),
      ]),
    );
    assert.equal(f.resolvedPath, path.join(root, 'Dockerfile'));
    assert.equal(f.line, 1);
    assert.equal(f.level, 'high');
    assert.equal(f.severityLabel, 'HIGH');
    assert.equal(f.severity, 'error');
    assert.equal(f.message, 'Missing user instruction');
  });

  it('leaves a bracketed prefix that is not a severity word alone', () => {
    const [f] = one(
      gate('bandit', [
        norm({ path: 'app.py', line: 1, message: '[B603] subprocess call' }, { path: 'app.py', line: 1, message: '[B603] subprocess call' }),
      ]),
    );
    assert.equal(f.level, 'unrated');
    assert.equal(f.message, '[B603] subprocess call');
  });

  it('places a location that gandalf scraped out of a raw tool line (mypy)', () => {
    const [f] = one(
      gate('mypy', [
        norm(
          { error: 'src/gandalf/__main__.py:465: error: "Gate" has no attribute "langs"  [attr-defined]' },
          { path: 'src/gandalf/__main__.py', line: 465, message: 'error: "Gate" has no attribute "langs"  [attr-defined]' },
        ),
      ]),
    );
    assert.equal(f.resolvedPath, path.join(root, 'src', 'gandalf', '__main__.py'));
    assert.equal(f.line, 465);
    assert.equal(f.message, 'error: "Gate" has no attribute "langs"  [attr-defined]');
  });

  it('keeps prose whose path gandalf would not vouch for', () => {
    const [f] = one(
      gate('grill_me', [
        norm(
          { finding: 'See docs/adr.md:1 for the rationale — no decision recorded' },
          { message: 'See docs/adr.md:1 for the rationale — no decision recorded' },
        ),
      ]),
    );
    assert.equal(f.resolvedPath, '', 'docs/adr.md does not exist, so gandalf sent no path');
    assert.equal(f.line, 0);
    assert.match(f.message, /^See docs/);
  });

  it('keeps a finding with no location at all (scorecard)', () => {
    const [f] = one(
      gate('scorecard', [
        norm(
          { check: 'Branch-Protection', score: 3, reason: 'branch protection not enabled' },
          { rule: 'Branch-Protection', message: 'branch protection not enabled' },
        ),
      ]),
    );
    assert.equal(f.resolvedPath, '');
    assert.equal(f.rule, 'Branch-Protection');
    assert.equal(f.message, 'branch protection not enabled');
  });

  it('reads a gate whose whole finding is one sentence in a location key', () => {
    const [f] = one(
      gate('format', [
        norm(
          { file: 'Would reformat: src/gandalf/__main__.py' },
          { path: 'src/gandalf/__main__.py', message: 'Would reformat: src/gandalf/__main__.py' },
        ),
      ]),
    );
    assert.equal(f.message, 'Would reformat: src/gandalf/__main__.py', 'not a JSON dump');
    assert.equal(f.resolvedPath, path.join(root, 'src', 'gandalf', '__main__.py'));
    assert.equal(f.line, 0, 'no line was reported, so it gets no squiggle');
  });

  it('falls back to the raw record when gandalf found nothing to say', () => {
    const [f] = one(gate('weird', [norm({ nothing_we_know: 'about' }, {})]));
    assert.match(f.message, /nothing_we_know/);
  });

  it('coerces a non-object finding', () => {
    const [f] = one(gate('odd', ['just a string' as unknown as RawFinding]));
    assert.equal(f.message, 'just a string');
  });

  it('surfaces a failing gate that reported no findings', () => {
    const [f] = one(gate('build', [], { outcome: 'fail', summary: 'build: 1 file(s) fail to compile' }));
    assert.equal(f.message, 'build: 1 file(s) fail to compile');
    assert.equal(f.severity, 'error');
  });

  it('says nothing about a passing gate with no findings', () => {
    assert.deepEqual(one(gate('ruff', [], { outcome: 'pass', summary: 'ruff clean' })), []);
  });

  it('gives each finding a stable id', () => {
    const build = () => one(gate('ruff', [norm({ path: 'app.py', line: 1, message: 'x' }, { path: 'app.py', line: 1, message: 'x' })]))[0].id;
    assert.equal(build(), build());
  });
});

/**
 * A gandalf older than `findings.py` sends no `_gandalf` block. The pane must
 * still be usable; it just loses the reconciliation gandalf would have done.
 */
describe('a gandalf that predates the normalizer', () => {
  it('still reads the classic keys', () => {
    const [f] = one(gate('ruff', [{ filename: 'app.py', line: 3, code: 'E501', message: 'line too long' }]));
    assert.equal(f.rule, 'E501');
    assert.equal(f.line, 3);
    assert.equal(f.resolvedPath, path.join(root, 'app.py'));
  });

  it('still identifies bandit by its test id', () => {
    const [f] = one(gate('bandit', [{ filename: 'app.py', line_number: 1, test_id: 'B105', issue_text: 'pw', code: '1 x\n2 y' }]));
    assert.equal(f.rule, 'B105');
  });

  it('degrades quietly where it cannot reconcile', () => {
    // Nested positions, prose scraping and folded-in severities are gandalf's
    // job now, so an old build simply reports the finding unplaced.
    const [f] = one(gate('ruff', [{ filename: 'app.py', location: { row: 9 }, message: 'x' }]));
    assert.equal(f.line, 0, 'listed in the pane, just without a squiggle');
    assert.equal(f.resolvedPath, path.join(root, 'app.py'));
  });
});

describe('reported level', () => {
  const levelOf = (severity: string, outcome: RawGate['outcome'] = 'warn') =>
    one(
      gate('g', [norm({ path: 'app.py', line: 1, message: 'x' }, { path: 'app.py', line: 1, message: 'x', severity })], {
        outcome,
      }),
    )[0];

  it("places each of gandalf's severities on the ladder", () => {
    // The vocabulary itself — which tool words map to which of these — is
    // gandalf's, and is tested in tests/test_findings.py.
    const cases: [string, string][] = [
      ['critical', 'critical'],
      ['high', 'high'],
      ['medium', 'medium'],
      ['low', 'low'],
      ['info', 'info'],
      ['unknown', 'unrated'],
      ['', 'unrated'],
    ];
    for (const [word, level] of cases) assert.equal(levelOf(word).level, level, word || '(none)');
  });

  it('keeps critical distinct from high, though both squiggle as errors', () => {
    assert.equal(levelOf('critical').severity, 'error');
    assert.equal(levelOf('high').severity, 'error');
    assert.notEqual(levelOf('critical').level, levelOf('high').level);
  });

  it('calls a finding with no severity unrated, not a guess', () => {
    const f = levelOf('');
    assert.equal(f.level, 'unrated');
    assert.equal(f.severityLabel, '', 'nothing to show as a level');
    assert.equal(f.severity, 'warning', 'but it still inherits the gate outcome');
  });

  it('sorts an unrated finding by the outcome it inherited', () => {
    // A failing gate's unrated finding must outrank a tool's LOW.
    assert.equal(sortLevel(levelOf('', 'fail')), 'high');
    assert.equal(sortLevel(levelOf('', 'warn')), 'medium');
    assert.equal(sortLevel(levelOf('low')), 'low', 'a rated one keeps its own level');
  });

  it('orders the pane worst-first across levels', () => {
    const at = (line: number, message: string, severity: string) =>
      norm({ path: 'app.py', line, message }, { path: 'app.py', line, message, severity });
    const findings = one(
      gate('a', [at(1, 'low', 'low')]),
      gate('b', [at(2, 'critical', 'critical')]),
      gate('c', [at(3, 'unrated-error', '')], { outcome: 'fail' }),
      gate('d', [at(4, 'medium', 'medium')]),
      gate('e', [at(5, 'high', 'high')]),
    );
    assert.deepEqual(
      findings.map((f) => f.message),
      ['critical', 'high', 'unrated-error', 'medium', 'low'],
    );
  });

  it('has a label for every level', () => {
    assert.equal(LEVELS.length, 6);
    assert.deepEqual(LEVELS, ['critical', 'high', 'medium', 'low', 'info', 'unrated']);
  });
});

describe('gates that assessed nothing', () => {
  const bare = () =>
    payloadOf(
      gate('trivy', [], { outcome: 'warn', summary: 'trivy unavailable (no host binary or gandalf-tools image) — skipped' }),
      gate('semgrep', [], { outcome: 'warn', summary: 'semgrep: did not run (timeout or tool unavailable) — skipped' }),
      gate('ci_act', [], { outcome: 'warn', summary: "'act' not found; CI not verified locally" }),
      gate('dalfox', [], { outcome: 'warn', summary: 'dalfox: no target URL — skipped (pass --target)' }),
      gate('compliance', [], { outcome: 'warn', summary: 'compliance: no request/diff to judge (pass --title/--body)' }),
      gate('ruff', [], { outcome: 'pass', summary: 'ruff clean' }),
      gate('mypy', [{ error: 'app.py:1: error: bad' }], { outcome: 'warn', summary: 'mypy: 1 issue(s)' }),
      gate('tests', [], { outcome: 'fail', summary: 'tests: 3 failure(s)' }),
    );

  it('separates blocked gates from inapplicable ones', () => {
    const { blocked, inapplicable } = gatesByStatus(bare());
    assert.deepEqual(blocked, ['trivy', 'semgrep', 'ci_act']);
    assert.deepEqual(inapplicable, ['dalfox', 'compliance']);
  });

  it('keeps them out of the findings list, but never hides a red gate', () => {
    const findings = normalize(bare(), root);
    assert.deepEqual(
      findings.map((f) => f.gate),
      ['tests', 'mypy'],
      'only the failing suite and the real mypy finding are listed',
    );
  });
});
