-- What the floats render, and what reaches vim.diagnostic.
--
-- The renderers are asserted on the lines they return, and publish() on the
-- diagnostics the editor can read back -- never on anything the module kept to
-- itself.

local ui = require('gandalf.ui')

local function finding(over)
  return vim.tbl_extend('force', {
    gate = 'ruff',
    category = 'Code quality',
    outcome = 'warn',
    level = 'medium',
    severity_label = 'MEDIUM',
    rule = 'E501',
    message = 'line too long',
    path = '',
    line = 0,
    column = 0,
    url = '',
    package = '',
    installed = '',
    fixed = '',
  }, over or {})
end

local function joined(lines)
  return table.concat(lines, '\n')
end

describe('the scorecard float', function()
  local function snapshot(over)
    return vim.tbl_extend('force', {
      payload = {
        verdict = 'warn',
        score = 71,
        scope = 'working tree',
        gates = {
          { name = 'ruff', outcome = 'warn', summary = 'ruff: 2 issue(s)', category = 'Code quality', findings = { {} } },
          { name = 'trivy', outcome = 'pass', summary = 'clean', category = 'Security', findings = {} },
        },
      },
      findings = { finding() },
      blocked = {},
      inapplicable = {},
    }, over or {})
  end

  it('leads with the verdict word, the score and the scope', function()
    local lines = ui.report_lines(snapshot())
    assert.equals('AMBER · 71/100    scope: working tree', lines[1])
  end)

  it('groups the gates under the categories the report gave them', function()
    local text = joined(ui.report_lines(snapshot()))
    assert.is_truthy(text:match('Code quality\n  ● ruff'))
    assert.is_truthy(text:match('Security\n  ● trivy'))
  end)

  it('never lets a green board mean a gate that could not run', function()
    local text = joined(ui.report_lines(snapshot({ blocked = { 'semgrep', 'gitleaks' } })))
    assert.is_truthy(text:match('Could not run'))
    assert.is_truthy(text:match('semgrep, gitleaks'))
  end)

  it('names what had nothing to assess separately from what was blocked', function()
    local text = joined(ui.report_lines(snapshot({ inapplicable = { 'terraform' } })))
    assert.is_truthy(text:match('Nothing to assess: terraform'))
    assert.is_falsy(text:match('Could not run'))
  end)

  it('keeps a gate that assessed nothing out of the category listing', function()
    local blocked_gate =
      { name = 'semgrep', outcome = 'warn', summary = 'semgrep: unavailable', category = 'Security', findings = {} }
    local snap = snapshot()
    table.insert(snap.payload.gates, blocked_gate)
    local text = joined(ui.report_lines(snap))
    assert.is_falsy(text:match('● semgrep'))
  end)

  it('counts the findings and spreads the summary over its own lines', function()
    local text = joined(ui.report_lines(snapshot({ payload = vim.tbl_extend('force', snapshot().payload, {
      summary = 'first line\nsecond line',
    }) })))
    assert.is_truthy(text:match('1 finding%(s%)'))
    assert.is_truthy(text:match('first line\nsecond line'))
  end)
end)

describe('the hover float', function()
  it('shows the installed version next to the package when a gate reported one', function()
    local lines = ui.hover_lines('flask', { finding({ package = 'flask', installed = '2.0.1' }) }, nil)
    assert.equals('flask  2.0.1', lines[1])
  end)

  it('falls back to the bare package name when nothing named a version', function()
    assert.equals('flask', ui.hover_lines('flask', { finding({ package = 'flask' }) }, nil)[1])
  end)

  it('says nothing was found, and how much of that is proof', function()
    local text = joined(ui.hover_lines('flask', {}, { blocked = { 'osv-scanner' } }))
    assert.is_truthy(text:match('No findings against this dependency'))
    assert.is_truthy(text:match('not proof of anything'))
    assert.is_truthy(text:match('osv%-scanner'))
  end)

  it('does not hedge when every gate ran', function()
    local text = joined(ui.hover_lines('flask', {}, { blocked = {} }))
    assert.is_truthy(text:match('No findings against this dependency'))
    assert.is_falsy(text:match('not proof of anything'))
  end)

  it('carries the fix and the advisory link onto the finding it belongs to', function()
    local text = joined(ui.hover_lines('flask', {
      finding({
        package = 'flask',
        severity_label = 'HIGH',
        rule = 'CVE-2023-30861',
        message = 'cookie leak',
        fixed = '2.2.5',
        url = 'https://example.invalid/CVE-2023-30861',
      }),
    }, nil))
    assert.is_truthy(text:match('● HIGH ruff · CVE%-2023%-30861'))
    assert.is_truthy(text:match('    fixed in: 2%.2%.5'))
    assert.is_truthy(text:match('    https://example%.invalid'))
  end)
end)

describe('publishing diagnostics', function()
  local cfg = require('gandalf.config').resolve({})
  local root, buf

  before_each(function()
    root = vim.fn.tempname()
    vim.fn.mkdir(vim.fs.joinpath(root, 'src'), 'p')
    local file = vim.fs.joinpath(root, 'src', 'a.py')
    vim.fn.writefile({ 'x = 1', 'y = 2', 'z = 3' }, file)
    buf = vim.fn.bufadd(file)
    vim.fn.bufload(buf)
  end)

  after_each(function()
    ui.clear()
    vim.api.nvim_buf_delete(buf, { force = true })
    vim.fn.delete(root, 'rf')
  end)

  local function published()
    return vim.diagnostic.get(buf, { namespace = ui.namespace })
  end

  it('places a finding on the line and column the gate named, zero-indexed', function()
    ui.publish({ finding({ path = 'src/a.py', line = 2, column = 3 }) }, cfg, root)
    local got = published()
    assert.equals(1, #got)
    assert.equals(1, got[1].lnum)
    assert.equals(2, got[1].col)
    assert.equals('gandalf', got[1].source)
  end)

  it('carries the gate and the category into the message, so a squiggle explains itself', function()
    ui.publish({ finding({ path = 'src/a.py', line = 1 }) }, cfg, root)
    assert.is_truthy(published()[1].message:match('gate: ruff · category: Code quality'))
  end)

  it('publishes nothing at all when diagnostics are switched off', function()
    local off = require('gandalf.config').resolve({ diagnostics = { enabled = false } })
    ui.publish({ finding({ path = 'src/a.py', line = 1 }) }, off, root)
    assert.equals(0, #published())
  end)

  it('drops a finding below the configured floor', function()
    local highs = require('gandalf.config').resolve({ diagnostics = { min_level = 'high' } })
    ui.publish({
      finding({ path = 'src/a.py', line = 1, level = 'critical' }),
      finding({ path = 'src/a.py', line = 2, level = 'low' }),
    }, highs, root)
    assert.equals(1, #published())
    assert.equals(0, published()[1].lnum)
  end)

  it('sorts an unrated finding by its gate outcome before applying the floor', function()
    -- A failing gate's unrated finding is implied HIGH, so a `high` floor keeps
    -- it; a passing gate's is implied INFO and goes.
    local highs = require('gandalf.config').resolve({ diagnostics = { min_level = 'high' } })
    ui.publish({
      finding({ path = 'src/a.py', line = 1, level = 'unrated', outcome = 'fail' }),
      finding({ path = 'src/a.py', line = 2, level = 'unrated', outcome = 'pass' }),
    }, highs, root)
    assert.equals(1, #published())
    assert.equals(0, published()[1].lnum)
  end)

  it('stops at max_per_file rather than drowning a pathological file', function()
    local capped = require('gandalf.config').resolve({ diagnostics = { max_per_file = 2 } })
    local many = {}
    for i = 1, 5 do
      many[i] = finding({ path = 'src/a.py', line = i })
    end
    ui.publish(many, capped, root)
    assert.equals(2, #published())
  end)

  it('keeps a finding with no place to put it out of the editor', function()
    ui.publish({ finding({ path = '', line = 0 }) }, cfg, root)
    assert.equals(0, #published())
  end)

  it('replaces the whole namespace, so a rescan never leaves a stale squiggle', function()
    ui.publish({ finding({ path = 'src/a.py', line = 1 }), finding({ path = 'src/a.py', line = 3 }) }, cfg, root)
    assert.equals(2, #published())
    ui.publish({ finding({ path = 'src/a.py', line = 1 }) }, cfg, root)
    assert.equals(1, #published())
  end)
end)

describe('the quickfix list', function()
  it('marks critical and high as errors and everything else as warnings', function()
    ui.to_quickfix({
      finding({ path = 'src/a.py', line = 4, column = 2, level = 'high' }),
      finding({ path = 'src/a.py', line = 5, column = 1, level = 'low' }),
    }, '/repo', 'Gandalf')
    local items = vim.fn.getqflist()
    assert.equals(2, #items)
    assert.equals('E', items[1].type)
    assert.equals('W', items[2].type)
    assert.equals(4, items[1].lnum)
    assert.equals(2, items[1].col)
  end)

  it('flattens a multi-line message, which the list shows one row per entry', function()
    ui.to_quickfix({ finding({ path = 'src/a.py', line = 1, message = 'first\nsecond' }) }, '/repo', 'Gandalf')
    assert.equals('[ruff] E501: first second', vim.fn.getqflist()[1].text)
  end)
end)
