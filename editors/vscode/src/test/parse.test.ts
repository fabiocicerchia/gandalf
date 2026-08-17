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

import { gatesByStatus, normalize, resolvePath } from '../parse';
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
    generated_at: '2026-08-15 10:00:00 UTC',
    commit: { short: 'abc1234', subject: 'test' },
    languages: ['python'],
    verdict: 'warn',
    passed: true,
    policy: { fail_on: 'fail', min_score: 0, reason: 'policy satisfied' },
    score: 70,
    summary: '',
    changeset: '',
    remediation: '',
    improvement: '',
    skipped_gates: [],
    disabled_gates: [],
    fixes: [],
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

describe('finding normalization', () => {
  it('reads ruff: filename + nested location.row/column + code + url', () => {
    const [f] = one(
      gate('ruff', [
        {
          filename: path.join(root, 'app.py'),
          code: 'E501',
          message: 'Line too long (100 > 88)',
          location: { row: 12, column: 89 },
          url: 'https://docs.astral.sh/ruff/rules/line-too-long',
        },
      ]),
    );
    assert.equal(f.rule, 'E501');
    assert.equal(f.line, 12);
    assert.equal(f.column, 89);
    assert.equal(f.resolvedPath, path.join(root, 'app.py'));
    assert.equal(f.url, 'https://docs.astral.sh/ruff/rules/line-too-long');
    assert.equal(f.severity, 'warning', 'no severity word → inherits the gate outcome');
  });

  it('reads semgrep: path + line + check_id + severity word', () => {
    const [f] = one(
      gate(
        'semgrep',
        [{ path: 'app.py', line: 3, check_id: 'python.lang.security.eval', message: 'eval() is dangerous', severity: 'ERROR' }],
        { outcome: 'fail', category: 'Security' },
      ),
    );
    assert.equal(f.severity, 'error');
    assert.equal(f.severityLabel, 'ERROR');
    assert.equal(f.rule, 'python.lang.security.eval');
    assert.equal(f.category, 'Security');
    assert.equal(f.line, 3);
  });

  it('reads kics: file + line + message', () => {
    const [f] = one(gate('kics', [{ file: 'Dockerfile', line: 1, message: '[HIGH] Missing user instruction' }]));
    assert.equal(f.resolvedPath, path.join(root, 'Dockerfile'));
    assert.equal(f.line, 1);
  });

  it('scrapes path:line out of a raw tool line (mypy)', () => {
    const [f] = one(
      gate('mypy', [{ error: 'src/gandalf/__main__.py:465: error: "Gate" has no attribute "langs"  [attr-defined]' }]),
    );
    assert.equal(f.resolvedPath, path.join(root, 'src', 'gandalf', '__main__.py'));
    assert.equal(f.line, 465);
    assert.equal(
      f.message,
      'error: "Gate" has no attribute "langs"  [attr-defined]',
      'the location is shown in its own column, so it is trimmed off the message',
    );
  });

  it('scrapes path:line:col out of a raw tool line (vulture)', () => {
    const [f] = one(gate('vulture', [{ finding: "app.py:2: unused variable 'y' (60% confidence)" }]));
    assert.equal(f.resolvedPath, path.join(root, 'app.py'));
    assert.equal(f.line, 2);
  });

  it('leaves prose alone when the scraped path is not a real file', () => {
    const [f] = one(gate('grill_me', [{ finding: 'See docs/adr.md:1 for the rationale — no decision recorded' }]));
    assert.equal(f.resolvedPath, '', 'docs/adr.md does not exist in this workspace');
    assert.equal(f.line, 0);
    assert.match(f.message, /^See docs/, 'the message is untouched');
  });

  it('keeps a finding with no location at all (scorecard)', () => {
    const [f] = one(gate('scorecard', [{ check: 'Branch-Protection', score: 3, reason: 'branch protection not enabled' }]));
    assert.equal(f.resolvedPath, '');
    assert.equal(f.rule, 'Branch-Protection');
    assert.equal(f.message, 'branch protection not enabled');
  });

  it('maps trivy-style capitalized keys', () => {
    const [f] = one(
      gate('licenses', [{ file: 'app.py', Severity: 'CRITICAL', message: 'GPL-3.0: some-package' }], { category: 'Licensing' }),
    );
    assert.equal(f.severity, 'error');
    assert.equal(f.severityLabel, 'CRITICAL');
  });

  it('reads a gate whose whole finding is one sentence in a location key', () => {
    // The format gate: [{"file": "Would reformat: src/gandalf/__main__.py"}]
    const [f] = one(gate('format', [{ file: 'Would reformat: src/gandalf/__main__.py' }]));
    assert.equal(f.message, 'Would reformat: src/gandalf/__main__.py', 'not a JSON dump');
    assert.equal(
      f.resolvedPath,
      path.join(root, 'src', 'gandalf', '__main__.py'),
      'the path inside the sentence still groups the row under its file',
    );
    assert.equal(f.line, 0, 'no line was reported, so it gets no squiggle');
  });

  it('does not mistake prose for a path', () => {
    const [f] = one(gate('grill_me', [{ finding: 'Consider splitting this up. It is too big.' }]));
    assert.equal(f.resolvedPath, '');
    assert.equal(f.message, 'Consider splitting this up. It is too big.');
  });

  it('falls back to the raw record when no key is recognizable', () => {
    const [f] = one(gate('weird', [{ nothing_we_know: 'about' }]));
    assert.equal(f.message, '{"nothing_we_know":"about"}');
  });

  it('coerces a non-object finding', () => {
    const [f] = one(gate('weird', ['just a string' as unknown as RawFinding]));
    assert.equal(f.message, 'just a string');
  });

  it('surfaces a failing gate that reported no findings', () => {
    const findings = one(gate('build', [], { outcome: 'fail', score: 0, summary: '1 file(s) fail to compile' }));
    assert.equal(findings.length, 1);
    assert.equal(findings[0].message, '1 file(s) fail to compile');
    assert.equal(findings[0].severity, 'error');
  });

  it('says nothing about a passing gate with no findings', () => {
    assert.equal(one(gate('ruff', [], { outcome: 'pass', score: 1, summary: 'ruff clean' })).length, 0);
  });

  it('sorts errors before warnings before info', () => {
    const findings = one(
      gate('a', [{ path: 'app.py', line: 1, message: 'low', severity: 'LOW' }]),
      gate('b', [{ path: 'app.py', line: 2, message: 'high', severity: 'HIGH' }]),
      gate('c', [{ path: 'app.py', line: 3, message: 'medium', severity: 'MEDIUM' }]),
    );
    assert.deepEqual(
      findings.map((f) => f.message),
      ['high', 'medium', 'low'],
    );
  });

  it('gives each finding a stable id', () => {
    const fixture = () => one(gate('ruff', [{ filename: 'app.py', code: 'E501', message: 'too long', line: 4 }]))[0].id;
    assert.equal(fixture(), fixture());
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
    assert.deepEqual(
      blocked.map((g) => g.name),
      ['trivy', 'semgrep', 'ci_act'],
    );
    assert.deepEqual(
      inapplicable.map((g) => g.name),
      ['dalfox', 'compliance'],
    );
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
