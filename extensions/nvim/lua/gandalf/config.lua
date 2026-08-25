-- Defaults, and the validation that turns a typo into a message at setup()
-- rather than a nil index inside a callback a minute into a scan.

local M = {}

M.defaults = {
  enabled = true,

  --- How to run gandalf. A list, so an interpreter can go in front of it:
  --- `{ 'python3', '-m', 'gandalf' }` for a checkout (with `env.PYTHONPATH`
  --- set), `{ 'gandalf' }` for the wrapper `make install` writes.
  cmd = { 'gandalf' },

  --- Extra environment for the CLI, merged over the inherited one. A source
  --- checkout needs PYTHONPATH; the LLM endpoint and tools image are read from
  --- here too.
  env = {},

  --- Path to a .gandalf.toml passed as --config. Point this at an
  --- editor-specific config to run a narrower gate set while you work: gate
  --- only/skip selection lives in the config file, not on the CLI.
  config_path = '',

  --- Paths no gate should read, as --exclude globs. A bare name skips that
  --- directory anywhere (`node_modules`), a path anchors at the repository
  --- root (`src/generated`), and globs work (`*.min.js`).
  exclude = {},

  --- Appended to every invocation, verbatim.
  extra_args = {},

  scan = {
    --- 'on_save' | 'on_save_and_interval' | 'interval' | 'manual'.
    --- gandalf never scans on a keystroke: gates spawn real tools.
    trigger = 'on_save',
    --- Quiet period after the triggering event. Later events restart it.
    debounce_ms = 1500,
    --- Period of the full-workspace sweep, for the interval triggers.
    interval_minutes = 15,
    --- One full scan when the plugin loads, so the list is populated.
    on_startup = true,
    --- Kill a run that exceeds this wall-clock budget.
    timeout_ms = 600000,
    --- Max gates at once (--concurrency). 0 leaves gandalf's default.
    concurrency = 0,
    --- Pass --cache on workspace scans so unchanged gates are reused.
    use_cache = true,
    --- Include the LLM summary in background scans. The report can always be
    --- regenerated with it on demand.
    llm = false,
    --- Read per-gate results as they land, so findings appear during the run
    --- rather than all at the end.
    stream = true,
  },

  diagnostics = {
    enabled = true,
    --- Lowest reported level published as a diagnostic.
    min_level = 'info',
    --- Reported level -> editor severity.
    severity = {
      critical = vim.diagnostic.severity.ERROR,
      high = vim.diagnostic.severity.ERROR,
      medium = vim.diagnostic.severity.WARN,
      low = vim.diagnostic.severity.INFO,
      info = vim.diagnostic.severity.INFO,
      unrated = vim.diagnostic.severity.HINT,
    },
    --- Backstop against a pathological file, not something worth tuning.
    max_per_file = 500,
  },
}

local function merge(defaults, opts)
  local out = {}
  for key, value in pairs(defaults) do
    if type(value) == 'table' and not vim.islist(value) then
      out[key] = merge(value, (opts or {})[key] or {})
    elseif opts and opts[key] ~= nil then
      out[key] = opts[key]
    else
      out[key] = value
    end
  end
  for key, value in pairs(opts or {}) do
    if out[key] == nil then
      out[key] = value
    end
  end
  return out
end

local TRIGGERS = {
  on_save = true,
  on_save_and_interval = true,
  interval = true,
  manual = true,
}

local LEVELS = { critical = true, high = true, medium = true, low = true, info = true, unrated = true }

local SEVERITIES = {
  [vim.diagnostic.severity.ERROR] = true,
  [vim.diagnostic.severity.WARN] = true,
  [vim.diagnostic.severity.INFO] = true,
  [vim.diagnostic.severity.HINT] = true,
}

function M.validate(cfg)
  vim.validate('enabled', cfg.enabled, 'boolean')
  vim.validate('cmd', cfg.cmd, function(v)
    return vim.islist(v) and #v > 0 and type(v[1]) == 'string'
  end, 'a non-empty list of strings')
  vim.validate('env', cfg.env, 'table')
  vim.validate('config_path', cfg.config_path, 'string')
  vim.validate('exclude', cfg.exclude, vim.islist, 'a list of globs')
  vim.validate('extra_args', cfg.extra_args, vim.islist, 'a list of arguments')
  vim.validate('scan.trigger', cfg.scan.trigger, function(v)
    return TRIGGERS[v] == true
  end, 'one of: ' .. table.concat(vim.tbl_keys(TRIGGERS), ', '))
  vim.validate('scan.debounce_ms', cfg.scan.debounce_ms, function(v)
    return type(v) == 'number' and v >= 250
  end, 'a number >= 250')
  vim.validate('scan.interval_minutes', cfg.scan.interval_minutes, function(v)
    return type(v) == 'number' and v >= 1
  end, 'a number >= 1')
  vim.validate('scan.on_startup', cfg.scan.on_startup, 'boolean')
  vim.validate('scan.timeout_ms', cfg.scan.timeout_ms, 'number')
  vim.validate('scan.concurrency', cfg.scan.concurrency, function(v)
    return type(v) == 'number' and v >= 0
  end, 'a number >= 0')
  vim.validate('scan.use_cache', cfg.scan.use_cache, 'boolean')
  vim.validate('scan.llm', cfg.scan.llm, 'boolean')
  vim.validate('scan.stream', cfg.scan.stream, 'boolean')
  vim.validate('diagnostics.enabled', cfg.diagnostics.enabled, 'boolean')
  vim.validate('diagnostics.min_level', cfg.diagnostics.min_level, function(v)
    return LEVELS[v] == true
  end, 'one of: critical, high, medium, low, info, unrated')
  vim.validate('diagnostics.max_per_file', cfg.diagnostics.max_per_file, 'number')
  for level, severity in pairs(cfg.diagnostics.severity) do
    vim.validate('diagnostics.severity.' .. level, severity, function(v)
      return v == false or SEVERITIES[v] == true
    end, 'false, or a vim.diagnostic.severity value')
  end
  return cfg
end

function M.resolve(opts)
  return M.validate(merge(M.defaults, opts or {}))
end

return M
