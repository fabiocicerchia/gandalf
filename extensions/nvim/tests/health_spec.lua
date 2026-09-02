-- :checkhealth gandalf, asserted on the report it renders.
--
-- vim.health is swapped for a recorder, so every assertion is about a line the
-- user would read. The docker, curl and git sections depend on the machine the
-- suite runs on and are deliberately not asserted; the gandalf-command section
-- is driven by pointing `cmd` at a stand-in whose --help output we choose.

local health = require('gandalf.health')

--- Stand-ins for the gandalf CLI, resolved rather than hard-coded so the specs
--- do not depend on where this machine keeps its coreutils.
local ECHO = vim.fn.exepath('echo')
local ABSENT = vim.fs.joinpath(vim.fn.tempname(), 'no-such-gandalf')

local recorded = {}

local function record(kind)
  return function(message, advice)
    recorded[#recorded + 1] = { kind = kind, message = message, advice = advice or {} }
  end
end

--- Every recorded line, so a match can be run over the whole report.
local function text()
  local out = {}
  for _, entry in ipairs(recorded) do
    out[#out + 1] = entry.kind .. ': ' .. entry.message
    for _, line in ipairs(entry.advice) do
      out[#out + 1] = '    ' .. line
    end
  end
  return table.concat(out, '\n')
end

--- Run :checkhealth against a gandalf command of our choosing.
local function check_with(cmd)
  recorded = {}
  require('gandalf').setup({
    cmd = cmd,
    scan = { trigger = 'manual', on_startup = false },
  })
  local real = vim.health
  vim.health = {
    start = record('start'),
    ok = record('ok'),
    warn = record('warn'),
    error = record('error'),
    info = record('info'),
  }
  local ok, err = pcall(health.check)
  vim.health = real
  assert(ok, err)
  return text()
end

describe('the gandalf command', function()
  it('says how to fix it when the command is not executable', function()
    local report = check_with({ ABSENT })
    assert.is_truthy(report:match('error: `' .. vim.pesc(ABSENT) .. '` is not executable'))
    assert.is_truthy(report:match('make install'))
    assert.is_truthy(report:match('PYTHONPATH'))
  end)

  it('does not take any runnable command for gandalf', function()
    local report = check_with({ ECHO })
    assert.is_truthy(report:match('ran, but does not look like gandalf'))
    assert.is_falsy(report:match('runs\n'))
  end)

  it('accepts a build that identifies itself, and reports what it can stream', function()
    local report = check_with({ ECHO, 'gandalf --stream' })
    assert.is_truthy(report:match('ok: `' .. vim.pesc(ECHO) .. ' gandalf %-%-stream` runs'))
    assert.is_truthy(report:match('ok: this build supports %-%-stream'))
  end)

  it('warns that findings will only arrive at the end when the build has no --stream', function()
    local report = check_with({ ECHO, 'gandalf 0.1.0' })
    assert.is_truthy(report:match('runs'))
    assert.is_truthy(report:match('warn: this build has no %-%-stream support'))
    assert.is_truthy(report:match('only appear when the whole run finishes'))
  end)
end)

describe('the environment', function()
  it('opens the section and states the Neovim it is judging', function()
    local report = check_with({ ECHO, 'gandalf' })
    assert.equals('start', recorded[1].kind)
    assert.equals('gandalf', recorded[1].message)
    assert.is_truthy(report:match('ok: Neovim '))
  end)

  it('names the project root it resolved, because that is what gandalf will scan', function()
    check_with({ ECHO, 'gandalf' })
    local root = require('gandalf').root()
    assert.is_truthy(text():find('info: project root: ' .. root, 1, true))
  end)

  it('confirms a git repository, since gandalf resolves its scope from one', function()
    -- The suite runs inside the gandalf checkout, so this is the repository case.
    assert.is_truthy(check_with({ ECHO, 'gandalf' }):match('ok: git repository'))
  end)
end)
