-- The scan loop, end to end, against a stand-in for the gandalf CLI.
--
-- `cmd` is a list, so a shell script can stand in for gandalf: it emits the
-- --stream events on stdout, a progress redraw on stderr, and the `JSON report:`
-- line that names the report it wrote. That exercises the whole of M.scan --
-- argv, streaming, the progress parser, the completion handler and the failure
-- paths -- without a python process or a real gate.

local gandalf = require('gandalf')

local dir

local function write(name, lines)
  local path = vim.fs.joinpath(dir, name)
  vim.fn.writefile(lines, path)
  return path
end

local REPORT = {
  verdict = 'pass',
  score = 88,
  scope = 'working tree',
  gates = {
    {
      name = 'ruff',
      outcome = 'warn',
      summary = 'ruff: 1 issue(s)',
      category = 'Code quality',
      findings = {
        {
          _gandalf = {
            path = 'src/a.py',
            line = 7,
            column = 1,
            rule = 'E501',
            message = 'line too long',
            severity = 'medium',
            url = '',
          },
        },
      },
    },
    { name = 'semgrep', outcome = 'warn', summary = 'semgrep: unavailable', category = 'Security', findings = {} },
  },
}

local GATE_EVENT = '{"event":"gate","name":"ruff","outcome":"warn","index":1,"total":2,'
  .. '"summary":"ruff: 1 issue(s)","category":"Code quality","findings":[{"_gandalf":'
  .. '{"path":"src/b.py","line":3,"column":1,"rule":"E999","message":"streamed",'
  .. '"severity":"high","url":""}}]}'

--- A stand-in gandalf that streams one gate, draws one progress line and names
--- the report it wrote.
local function fake_cli(report_path)
  return {
    '/bin/sh',
    write('gandalf.sh', {
      "printf '%s\\n' '{\"event\":\"start\",\"scope\":\"working tree\",\"gates\":2}'",
      ("printf '%%s\\n' '%s'"):format(GATE_EVENT),
      "printf '\\r\\033[K[2/3] Running 2 gates  [##] 1/2 ruff' >&2",
      "printf '%s\\n' 'GREEN 88/100'",
      ("printf '%%s\\n' 'JSON report: %s'"):format(report_path),
    }),
  }
end

--- Run one scan and block until it is finished. Returns whether it succeeded.
local function scan(opts)
  local done = nil
  gandalf.scan(vim.tbl_extend('force', { kind = 'workspace', manual = true }, opts or {}, {
    on_done = function(ok)
      done = ok
    end,
  }))
  assert(vim.wait(15000, function()
    return done ~= nil
  end, 20), 'the scan never finished')
  return done
end

--- The log lines this test appended, so an earlier test's failure cannot
--- satisfy a later test's assertion.
local log_mark = 0

local function log_since()
  local lines = gandalf.log_text()
  local out = {}
  for i = log_mark + 1, #lines do
    out[#out + 1] = lines[i]
  end
  return table.concat(out, '\n')
end

local function setup(cmd)
  gandalf.setup({ cmd = cmd, scan = { trigger = 'manual', on_startup = false, stream = true } })
  log_mark = #gandalf.log_text()
end

describe('a completed scan', function()
  local report_path

  before_each(function()
    dir = vim.fn.tempname()
    vim.fn.mkdir(dir, 'p')
    report_path = write('report.json', { vim.json.encode(REPORT) })
    setup(fake_cli(report_path))
  end)

  after_each(function()
    vim.fn.delete(dir, 'rf')
  end)

  it('reports success and keeps the report as the snapshot', function()
    assert.is_true(scan())
    local snapshot = gandalf.snapshot()
    assert.equals(88, snapshot.payload.score)
    assert.equals(report_path, snapshot.json_path)
  end)

  it('replaces the streamed gate with what the report finally said', function()
    assert.is_true(scan())
    local findings = gandalf.findings()
    assert.equals(1, #findings)
    -- The streamed event named src/b.py; the report is the whole truth.
    assert.equals('src/a.py', findings[1].path)
    assert.equals('E501', findings[1].rule)
  end)

  it('shows a streamed gate before the report lands', function()
    local streamed
    gandalf.scan({
      kind = 'workspace',
      manual = true,
      on_gate = function(event)
        streamed = { event = event, findings = gandalf.findings() }
      end,
      on_done = function() end,
    })
    assert(vim.wait(15000, function()
      return streamed ~= nil and not gandalf.is_scanning()
    end, 20), 'the scan never finished')
    assert.equals('ruff', streamed.event.name)
    assert.equals(1, #streamed.findings)
    assert.equals('src/b.py', streamed.findings[1].path)
  end)

  it('splits out the gates that assessed nothing, so green never means unchecked', function()
    assert.is_true(scan())
    assert.same({ 'semgrep' }, gandalf.snapshot().blocked)
  end)

  it('reads the verdict and the score into the status line', function()
    assert.is_true(scan())
    assert.equals('gandalf GREEN 88/100', gandalf.statusline())
  end)

  it('stops calling itself busy once the run is over', function()
    assert.is_true(scan())
    assert.is_false(gandalf.is_scanning())
  end)

  it('logs the command it ran and the verdict it got', function()
    assert.is_true(scan())
    assert.is_truthy(log_since():match('scan %(command%): /bin/sh .* %-%-no%-html'))
    assert.is_truthy(log_since():match('done: pass 88/100, 1 finding%(s%)'))
  end)
end)

describe('a scan that produced nothing', function()
  before_each(function()
    dir = vim.fn.tempname()
    vim.fn.mkdir(dir, 'p')
  end)

  after_each(function()
    vim.fn.delete(dir, 'rf')
  end)

  it('fails the run when no report line was printed', function()
    -- Exit 1 is a red verdict, which is normal. No report at all is not.
    setup({ '/bin/sh', write('quiet.sh', { "echo 'gandalf: exploded' >&2", 'exit 1' }) })
    assert.is_false(scan())
    assert.is_truthy(log_since():match('gandalf produced no report %(exit 1%)'))
    assert.is_truthy(log_since():match('gandalf: exploded'))
  end)

  it('fails the run when the report it named is not readable JSON', function()
    local broken = write('broken.json', { 'not json' })
    setup({ '/bin/sh', write('broken.sh', { ("printf '%%s\\n' 'JSON report: %s'"):format(broken) }) })
    assert.is_false(scan())
    assert.is_truthy(log_since():match('could not read the report gandalf wrote at ' .. vim.pesc(broken)))
  end)

  it('says the command could not be run at all', function()
    setup({ '/nonexistent/gandalf' })
    assert.is_false(scan())
    assert.is_truthy(log_since():match('could not run /nonexistent/gandalf'))
  end)
end)

describe('the scan policy', function()
  before_each(function()
    dir = vim.fn.tempname()
    vim.fn.mkdir(dir, 'p')
  end)

  after_each(function()
    gandalf.cancel({ quiet = true })
    vim.fn.delete(dir, 'rf')
  end)

  it('does nothing at all when the plugin is disabled', function()
    gandalf.setup({ enabled = false })
    local done = 'untouched'
    gandalf.scan({ kind = 'workspace', on_done = function(ok)
      done = ok
    end })
    assert.equals('untouched', done)
    assert.is_false(gandalf.is_scanning())
  end)

  --- A stand-in that records its own pid, so a preempted run can be shown dead.
  local function slow_cli()
    local pids = vim.fs.joinpath(dir, 'pids')
    return { '/bin/sh', write('slow.sh', { ('echo $$ >> %s'):format(pids), 'sleep 5' }) }, pids
  end

  local function started_pids(path)
    assert(vim.wait(5000, function()
      return vim.uv.fs_stat(path) ~= nil and #vim.fn.readfile(path) > 0
    end, 20), 'the stand-in never started')
    return vim.fn.readfile(path)
  end

  local function scans_logged()
    local n = 0
    for _ in log_since():gmatch('scan %(') do
      n = n + 1
    end
    return n
  end

  it('never queues an automatic scan behind a running one', function()
    local cmd, pids = slow_cli()
    setup(cmd)
    gandalf.scan({ kind = 'workspace', manual = true, on_done = function() end })
    started_pids(pids)
    gandalf.scan({ kind = 'file', rel_path = 'a.py', on_done = function() end })
    assert.equals(1, scans_logged())
    assert.is_falsy(log_since():match('preempting'))
  end)

  it('lets a manual scan preempt the one in flight, and kills what it preempted', function()
    local cmd, pids = slow_cli()
    setup(cmd)
    gandalf.scan({ kind = 'workspace', manual = true, on_done = function() end })
    local first = tonumber(started_pids(pids)[1])
    gandalf.scan({ kind = 'workspace', manual = true, on_done = function() end })
    assert.equals(2, scans_logged())
    assert.is_truthy(log_since():match('preempting the running scan'))
    -- Signal delivery is not instant.
    assert(vim.wait(5000, function()
      return not vim.uv.kill(first, 0)
    end, 20), ('the preempted run (%d) survived'):format(first))
    assert.is_true(gandalf.is_scanning())
  end)

  it('cancelling clears the run without failing it', function()
    setup({ '/bin/sh', write('slow.sh', { 'sleep 5' }) })
    gandalf.scan({ kind = 'workspace', manual = true, on_done = function() end })
    gandalf.cancel({ quiet = true })
    assert.is_false(gandalf.is_scanning())
    assert.is_falsy(log_since():match('scan failed'))
  end)
end)

describe('score over time', function()
  local real_select, offered

  before_each(function()
    dir = vim.fn.tempname()
    vim.fn.mkdir(dir, 'p')
    setup({ '/bin/echo' })
    real_select = vim.ui.select
    offered = nil
    vim.ui.select = function(items, opts, on_choice)
      offered = { items = items, opts = opts }
      on_choice(nil)
    end
  end)

  after_each(function()
    vim.ui.select = real_select
    vim.fn.delete(dir, 'rf')
  end)

  local function history()
    gandalf.history()
    assert(vim.wait(15000, function()
      return offered ~= nil
    end, 20), 'the picker was never offered')
    return offered
  end

  it('offers the commits git log reported, newest first', function()
    -- The suite runs inside the gandalf checkout, so `git log` has real commits.
    local picker = history()
    assert.is_true(#picker.items > 1)
    assert.is_truthy(picker.items[1].short:match('^%x+$'))
  end)

  it('says nothing has been scanned when the trend log is empty', function()
    local picker = history()
    assert.is_truthy(picker.opts.prompt:match('nothing scanned yet of %d+ commit%(s%)'))
    assert.equals('— not scanned', picker.opts.format_item(picker.items[1]):match('— not scanned'))
  end)
end)
