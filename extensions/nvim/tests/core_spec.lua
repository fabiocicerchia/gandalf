-- The ported logic, tested without an editor.

local core = require('gandalf.core')

local function gate(over)
  return vim.tbl_extend('force', {
    name = 'ruff',
    outcome = 'warn',
    score = 0.5,
    summary = 'ruff: 2 issue(s)',
    findings = {},
    category = 'Code quality',
  }, over or {})
end

--- A finding as gandalf now delivers it: the tool's own keys, plus the
--- `_gandalf` block findings.py computed from them.
local function norm(raw, block)
  return vim.tbl_extend('force', raw, {
    _gandalf = vim.tbl_extend('force', {
      path = '',
      line = 0,
      column = 0,
      rule = '',
      message = '',
      severity = '',
      url = '',
    }, block),
  })
end

describe('the command line', function()
  local cfg = require('gandalf.config').resolve({})

  it('never renders HTML and never writes to the trend log', function()
    local argv = core.scan_argv(cfg, { kind = 'workspace' })
    assert.is_true(vim.tbl_contains(argv, '--no-html'))
    assert.is_true(vim.tbl_contains(argv, '--no-trend'))
    assert.is_true(vim.tbl_contains(argv, '--no-llm'))
  end)

  it('scopes a file scan with --path, and uses forward slashes', function()
    local argv = core.scan_argv(cfg, { kind = 'file', rel_path = 'src\\a.py' })
    assert.is_true(vim.tbl_contains(argv, '--path'))
    assert.is_true(vim.tbl_contains(argv, 'src/a.py'))
  end)

  it('lets a named commit into the trend log, because that is what it is for', function()
    local argv = core.scan_argv(cfg, { kind = 'commit', commit = 'abc1234' })
    assert.is_true(vim.tbl_contains(argv, '--commit'))
    assert.is_false(vim.tbl_contains(argv, '--no-trend'))
  end)

  it('caches only whole-tree scans', function()
    -- A one-file scan would overwrite the workspace cache entries with a
    -- one-file hash and make the next full scan a complete miss.
    assert.is_true(vim.tbl_contains(core.scan_argv(cfg, { kind = 'workspace' }), '--cache'))
    assert.is_false(vim.tbl_contains(core.scan_argv(cfg, { kind = 'file', rel_path = 'a.py' }), '--cache'))
  end)

  it('asks for the LLM summary only when told to', function()
    assert.is_false(vim.tbl_contains(core.scan_argv(cfg, { kind = 'workspace', llm = true }), '--no-llm'))
  end)

  -- An older gandalf rejects an unknown flag with exit 2, so a flag it does not
  -- have fails the whole scan rather than being ignored. `--help` is what the
  -- caller probes; these three cases pin what argv does with the answer.
  describe('a build that does not take every flag', function()
    local with_excludes = require('gandalf.config').resolve({ exclude = { 'node_modules' } })
    local GATED = { '--out-dir', '--no-trend', '--cache', '--stream', '--exclude' }

    local function argv_with(flags)
      return core.scan_argv(with_excludes, {
        kind = 'workspace',
        out_dir = '/tmp/out',
        stream = true,
        flags = flags,
      })
    end

    it('withholds every optional flag the build did not report', function()
      local argv = argv_with({})
      for _, flag in ipairs(GATED) do
        assert.is_false(vim.tbl_contains(argv, flag), flag .. ' was passed to a build that has no such flag')
      end
    end)

    it('still passes the flags gandalf has always had', function()
      local argv = argv_with({})
      assert.is_true(vim.tbl_contains(argv, '--no-llm'))
      assert.is_true(vim.tbl_contains(argv, '--no-html'))
    end)

    it('passes them all when the build reported them, and when nobody probed', function()
      local reported = {}
      for _, flag in ipairs(GATED) do
        reported[flag] = true
      end
      for _, argv in ipairs({ argv_with(reported), argv_with(nil) }) do
        for _, flag in ipairs(GATED) do
          assert.is_true(vim.tbl_contains(argv, flag), flag .. ' was withheld from a build that takes it')
        end
      end
    end)
  end)

  it('repeats --exclude rather than joining, since a path may contain a comma', function()
    local with = require('gandalf.config').resolve({ exclude = { 'node_modules', 'src/generated' } })
    local argv = core.scan_argv(with, { kind = 'workspace' })
    local count = 0
    for _, arg in ipairs(argv) do
      if arg == '--exclude' then
        count = count + 1
      end
    end
    assert.equals(2, count)
  end)
end)

describe('reading a finding', function()
  it("reads gandalf's own reconciliation", function()
    local raw = norm({ filename = 'src/a.py', location = { row = 12 } }, {
      path = 'src/a.py',
      line = 12,
      column = 4,
      rule = 'E501',
      message = 'line too long',
    })
    local n = core.read_finding(raw)
    assert.equals('src/a.py', n.path)
    assert.equals(12, n.line)
    assert.equals('E501', n.rule)
  end)

  it('identifies a bandit finding by its test id, not its source snippet', function()
    -- The regression that moved this reconciliation into gandalf: `code` is the
    -- offending source, and it used to win over `test_id`.
    local raw = norm({
      filename = 'app.py',
      line_number = 42,
      test_id = 'B105',
      code = '41 def login():\n42     password = "hunter2"\n',
    }, { path = 'app.py', line = 42, rule = 'B105', message = 'hardcoded password', severity = 'high' })
    local n = core.read_finding(raw)
    assert.equals('B105', n.rule)
    assert.is_nil(n.rule:find('\n'))
  end)

  it('falls back for a gandalf that predates findings.py', function()
    local n = core.read_finding({ filename = 'a.py', line_number = 3, test_id = 'B105', issue_text = 'pw' })
    assert.equals('a.py', n.path)
    assert.equals(3, n.line)
    assert.equals('B105', n.rule, 'even the fallback puts test_id ahead of code')
    assert.equals('pw', n.message)
  end)

  it('survives a finding that is not a table at all', function()
    local n = core.read_finding('a bare string')
    assert.equals('a bare string', n.message)
    assert.equals(0, n.line)
  end)
end)

describe('the ladder', function()
  local function finding(severity, outcome)
    return core.normalize_gate(gate({
      outcome = outcome or 'warn',
      findings = { norm({}, { path = 'a.py', line = 1, message = 'x', severity = severity }) },
    }))[1]
  end

  it("places each of gandalf's severities on it", function()
    for word, level in pairs({
      critical = 'critical',
      high = 'high',
      medium = 'medium',
      low = 'low',
      info = 'info',
      unknown = 'unrated',
      [''] = 'unrated',
    }) do
      assert.equals(level, finding(word).level, word == '' and '(none)' or word)
    end
  end)

  it('shows a level it recognises, and nothing when it does not', function()
    assert.equals('HIGH', finding('high').severity_label)
    assert.equals('', finding('').severity_label, 'nothing to show is better than a guess')
  end)

  it('sorts an unrated finding by the outcome it inherited', function()
    -- A failing gate's unrated finding must outrank a tool's LOW.
    assert.equals('high', core.sort_level(finding('', 'fail')))
    assert.equals('medium', core.sort_level(finding('', 'warn')))
    assert.equals('low', core.sort_level(finding('low')), 'a rated one keeps its own level')
  end)

  it('orders worst-first across levels', function()
    local payload = {
      gates = {
        gate({ name = 'a', findings = { norm({}, { path = 'a.py', line = 1, message = 'low', severity = 'low' }) } }),
        gate({ name = 'b', findings = { norm({}, { path = 'a.py', line = 2, message = 'crit', severity = 'critical' }) } }),
        gate({ name = 'c', outcome = 'fail', findings = { norm({}, { path = 'a.py', line = 3, message = 'unrated' }) } }),
        gate({ name = 'd', findings = { norm({}, { path = 'a.py', line = 4, message = 'med', severity = 'medium' }) } }),
      },
    }
    assert.same(
      { 'crit', 'unrated', 'med', 'low' },
      vim.tbl_map(function(f)
        return f.message
      end, core.normalize(payload))
    )
  end)
end)

describe('gates that assessed nothing', function()
  local payload = {
    gates = {
      gate({ name = 'trivy', findings = {}, summary = 'trivy unavailable (no host binary or gandalf-tools image) — skipped' }),
      gate({ name = 'ci_act', findings = {}, summary = "'act' not found; CI not verified locally" }),
      gate({ name = 'dalfox', findings = {}, summary = 'dalfox: no target URL — skipped (pass --target)' }),
      gate({ name = 'ruff', findings = {}, outcome = 'pass', summary = 'ruff clean' }),
      gate({ name = 'tests', findings = {}, outcome = 'fail', summary = 'tests: 3 failure(s)' }),
    },
  }

  it('separates what could not run from what had nothing to do', function()
    local blocked, inapplicable = core.gates_by_status(payload)
    assert.same({ 'trivy', 'ci_act' }, blocked)
    assert.same({ 'dalfox' }, inapplicable)
  end)

  it('never hides a red gate, whatever its summary says', function()
    local findings = core.normalize(payload)
    assert.equals(1, #findings)
    assert.equals('tests', findings[1].gate)
    assert.equals('tests: 3 failure(s)', findings[1].message, 'the summary is the whole story')
  end)

  it('says nothing about a passing gate with no findings', function()
    assert.same({}, core.normalize({ gates = { gate({ outcome = 'pass', findings = {} }) } }))
  end)
end)

describe('--stream events', function()
  local function parser()
    return core.event_parser(vim.json.decode)
  end

  it('reads a start and a gate', function()
    local events = parser().feed('{"event":"start","scope":"working-tree","gates":3}\n')
    assert.equals(1, #events)
    assert.equals('start', events[1].event)
    assert.equals(3, events[1].gates)
  end)

  it('survives a chunk boundary mid-line', function()
    local p = parser()
    local line = '{"event":"gate","index":1,"total":3,"name":"ruff","outcome":"warn","findings":[]}'
    local first = p.feed(line:sub(1, 20))
    assert.equals(0, #first, 'nothing is emitted from half a line')
    local second = p.feed(line:sub(21) .. '\n')
    assert.equals(1, #second)
    assert.equals('ruff', second[1].name)
  end)

  it('hands back the scorecard text untouched', function()
    local _, text = parser().feed('JSON report: /tmp/x.json\n')
    assert.equals('JSON report: /tmp/x.json\n', text)
  end)

  it('does not let a malformed line poison the run', function()
    local events, text = parser().feed('{"event":"gate" this is not json\n')
    assert.equals(0, #events)
    assert.is_truthy(text:find('not json'), 'it stays readable instead')
  end)

  it('rejects an event missing what makes it one', function()
    local events = parser().feed('{"event":"gate","name":"ruff"}\n')
    assert.equals(0, #events, 'no outcome, so not a gate result')
  end)
end)

describe('the progress line', function()
  it('reads a stage and its gate bar', function()
    local p = core.parse_progress('[2/3] Running 37 gates  [███░░░] 12/37 semgrep')
    assert.equals('Running 37 gates', p.stage)
    assert.equals(12, p.gates_done)
    assert.equals(37, p.gates_total)
    assert.equals('semgrep', p.gate)
    -- Stage 2 of 3 has started, so 1 of 3 is behind us, plus 12/37 of this one.
    assert.is_true(p.percent > 44 and p.percent < 45)
  end)

  it('strips the escape codes gandalf redraws with', function()
    local p = core.parse_progress('\27[K[1/3] Resolving scope')
    assert.equals('Resolving scope', p.stage)
    assert.equals(0, p.gates_total)
  end)

  it('is not fooled by a line that is not progress', function()
    assert.is_nil(core.parse_progress('Traceback (most recent call last):'))
    assert.is_nil(core.parse_progress(''))
  end)

  it('separates progress from real stderr', function()
    local p = core.progress_parser()
    local state, noise = p.feed('[1/3] Resolving scope\rTraceback (most recent call last):\n')
    assert.equals('Resolving scope', state.stage)
    assert.is_truthy(noise:find('Traceback'))
  end)

  it('reads redraws separated by carriage returns', function()
    local p = core.progress_parser()
    local state = p.feed('[2/3] Running 3 gates  [█░░] 1/3 ruff\r[2/3] Running 3 gates  [██░] 2/3 mypy\r')
    assert.equals(2, state.gates_done, 'the newest redraw wins')
    assert.equals('mypy', state.gate)
  end)

  it('describes itself for a status line', function()
    assert.equals(
      'gates 12/37 · semgrep',
      core.describe_progress(core.parse_progress('[2/3] Running 37 gates  [█░] 12/37 semgrep'))
    )
    assert.equals('Resolving scope', core.describe_progress(core.parse_progress('[1/3] Resolving scope')))
  end)
end)

describe('score over time', function()
  it('takes the last line for a commit, because the log is append-only', function()
    local text = table.concat({
      '{"commit":"abc1234","score":70,"generated_at":"2026-01-01"}',
      '{"commit":"def5678","score":80,"generated_at":"2026-01-02"}',
      '{"commit":"abc1234","score":75,"generated_at":"2026-01-03"}',
    }, '\n')
    local trend = core.parse_trend(text, vim.json.decode)
    assert.equals(75, trend.abc1234.score, 'the rescan wins')
    assert.equals(80, trend.def5678.score)
  end)

  it('ignores a truncated final line', function()
    local trend = core.parse_trend('{"commit":"a","score":1}\n{"commit":"b","sco', vim.json.decode)
    assert.equals(1, vim.tbl_count(trend))
  end)

  it('reads git log with its unit separators', function()
    local commits = core.parse_log('abc1234\31fix: thing\0312026-01-01\ndef5678\31feat: other\0312026-01-02')
    assert.equals(2, #commits)
    assert.equals('abc1234', commits[1].short)
    assert.equals('fix: thing', commits[1].subject)
  end)

  it('scales the sparkline across the observed range, not 0-100', function()
    -- The interesting movement in a repo that sits in the eighties is within
    -- those eighties.
    local line = core.sparkline({ 80, 90 })
    assert.equals(vim.fn.strcharlen(line), 2)
    assert.are_not.equals(vim.fn.strcharpart(line, 0, 1), vim.fn.strcharpart(line, 1, 1))
    assert.equals('', core.sparkline({}))
  end)

  it('does not divide by zero on a flat history', function()
    assert.equals(vim.fn.strcharlen(core.sparkline({ 70, 70, 70 })), 3)
  end)

  it('reports the delta, and says so when there is none', function()
    assert.equals('+5', core.delta(75, 70))
    assert.equals('-5', core.delta(70, 75))
    assert.equals('±0', core.delta(70, 70))
    assert.equals('', core.delta(70, nil), 'the first scored commit has nothing to compare to')
  end)
end)

describe('the dependency under the cursor', function()
  it('reads the manifest formats people actually have open', function()
    local cases = {
      -- requirements.txt
      { 'flask==2.0.1', 'flask' },
      { '  flask>=1.0', 'flask' },
      { 'flask[async]==2.0', 'flask' },
      { 'python-dateutil', 'python-dateutil' },
      -- package.json, including a scoped name
      { '    "express": "^4.18.0",', 'express' },
      { '    "@types/node": "^20.0.0",', '@types/node' },
      -- go.mod
      { '\tgithub.com/spf13/cobra v1.8.0', 'github.com/spf13/cobra' },
      -- Cargo.toml
      { 'serde = "1.0"', 'serde' },
      { 'tokio = { version = "1", features = ["full"] }', 'tokio' },
      -- pyproject.toml -- the quoted requirement wins over the `key =`
      { 'dependencies = ["flask>=2.0"]', 'flask' },
      -- Gemfile
      { "gem 'rails', '~> 7.0'", 'rails' },
    }
    for _, case in ipairs(cases) do
      assert.equals(case[2], core.package_at_cursor(case[1]), 'for: ' .. case[1])
    end
  end)

  it('names nothing on a line that is not a dependency', function()
    for _, line in ipairs({ '', '   ', '# a comment', '// a comment', '[tool.poetry]', '-r base.txt' }) do
      assert.equals('', core.package_at_cursor(line), 'for: ' .. line)
    end
  end)

  it('finds the package on a finding however its tool spelled it', function()
    -- trivy
    assert.equals('express', core.finding_package({ PkgName = 'express' }))
    assert.equals('express', core.finding_package({ PkgID = 'express@4.17.1' }))
    -- osv-scanner nests it inside each affected range
    assert.equals('flask', core.finding_package({ affected = { { package = { name = 'flask' } } } }))
    -- a bare `name` is the rule on most gates, so it must not be read as one
    assert.equals('', core.finding_package({ name = 'CKV_AWS_1' }))
    assert.equals('', core.finding_package('a raw line'))
  end)

  it('matches findings to a package regardless of case', function()
    local findings = {
      { package = 'Express', message = 'a' },
      { package = 'express', message = 'b' },
      { package = 'flask', message = 'c' },
      { package = '', message = 'd' },
    }
    assert.equals(2, #core.findings_for_package(findings, 'EXPRESS'))
    assert.equals(0, #core.findings_for_package(findings, 'django'))
  end)

  it('carries the package through normalization', function()
    local gate_ = gate({
      name = 'trivy',
      findings = {
        norm({ PkgName = 'express', InstalledVersion = '4.17.1', FixedVersion = '4.19.2' }, {
          rule = 'CVE-2024-29041',
          message = 'Express.js open redirect',
          severity = 'high',
        }),
      },
    })
    local out = core.normalize_gate(gate_)
    assert.equals('express', out[1].package)
    assert.equals('4.17.1', out[1].installed)
    assert.equals('4.19.2', out[1].fixed)
  end)

  it('reads pip-audit fix_versions, which is a list', function()
    assert.equals('2.0.1, 2.1.0', core.normalize_gate(gate({
      name = 'osv',
      findings = { norm({ package = 'flask', fix_versions = { '2.0.1', '2.1.0' } }, { rule = 'PYSEC-1' }) },
    }))[1].fixed)
  end)
end)
