local config = require('gandalf.config')

describe('defaults', function()
  it('resolves without options', function()
    local cfg = config.resolve()
    assert.same({ 'gandalf' }, cfg.cmd)
    assert.equals('on_save', cfg.scan.trigger)
    assert.is_false(cfg.scan.llm)
    assert.is_true(cfg.scan.stream)
  end)

  it('never scans on a keystroke', function()
    -- There is no such trigger, deliberately: gates spawn real tools.
    local ok = pcall(config.resolve, { scan = { trigger = 'on_type' } })
    assert.is_false(ok)
  end)
end)

describe('merging', function()
  it('keeps siblings when one nested key is set', function()
    local cfg = config.resolve({ scan = { trigger = 'manual' } })
    assert.equals('manual', cfg.scan.trigger)
    assert.equals(1500, cfg.scan.debounce_ms)
  end)

  it('replaces a list wholesale', function()
    assert.same({ 'node_modules' }, config.resolve({ exclude = { 'node_modules' } }).exclude)
  end)

  it('lets a level be silenced', function()
    local cfg = config.resolve({ diagnostics = { severity = { info = false } } })
    assert.is_false(cfg.diagnostics.severity.info)
    assert.equals(vim.diagnostic.severity.ERROR, cfg.diagnostics.severity.high)
  end)
end)

describe('validation', function()
  local function fails(opts)
    local ok, err = pcall(config.resolve, opts)
    assert.is_false(ok, 'expected this to be rejected')
    return tostring(err)
  end

  it('rejects an empty cmd', function()
    assert.is_truthy(fails({ cmd = {} }):match('cmd'))
  end)

  it('rejects a trigger it does not have', function()
    assert.is_truthy(fails({ scan = { trigger = 'sometimes' } }):match('trigger'))
  end)

  it('rejects a debounce too short to collapse a burst of saves', function()
    assert.is_truthy(fails({ scan = { debounce_ms = 10 } }):match('debounce_ms'))
  end)

  it('rejects a level that is not on the ladder', function()
    assert.is_truthy(fails({ diagnostics = { min_level = 'catastrophic' } }):match('min_level'))
  end)

  it('accepts a source checkout, which is the awkward shape', function()
    assert.has_no.errors(function()
      config.resolve({
        cmd = { 'python3', '-m', 'gandalf' },
        env = { PYTHONPATH = '/p/gandalf/src' },
        scan = { trigger = 'manual', concurrency = 4 },
      })
    end)
  end)
end)
