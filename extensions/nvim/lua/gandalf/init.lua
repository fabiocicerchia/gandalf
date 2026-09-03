-- setup(), the triggers, and the public API.
--
-- A gandalf run forks ~30 gates, several of them `docker run`. That is not
-- something to do on a keystroke, so every trigger funnels through here: a burst
-- of saves is debounced into one run, and the scan policy itself lives in
-- `scan.lua`.
--
--   state.lua     what the plugin knows right now
--   scan.lua      running gandalf once
--   commands.lua  what the :Gandalf* commands do
--   ui.lua        diagnostics, the floats and the quickfix list
--   core/         reading what gandalf says, with no editor in it
--
-- Everything the README and `doc/gandalf.txt` name is re-exported here, so
-- `require('gandalf').<anything>` keeps working.

local commands = require('gandalf.commands')
local config = require('gandalf.config')
local scan = require('gandalf.scan')
local state = require('gandalf.state')
local ui = require('gandalf.ui')

local M = {}

--- Let the session settle before forking ~30 gates.
local STARTUP_DELAY_MS = 5000

local debounce_timer = nil
local sweep_timer = nil

-- --- the public API ----------------------------------------------------------

M.is_setup = state.is_setup
M.config = state.config
M.log_text = state.log_text
M.snapshot = state.snapshot
M.is_scanning = state.is_scanning
M.findings = state.findings
M.statusline = state.statusline
M.root = scan.root
M.cancel = scan.cancel

M.report = commands.report
M.hover = commands.hover
M.list = commands.list
M.filter = commands.filter
M.timings = commands.timings
M.history = commands.history
M.show_log = commands.show_log

function M.scan(opts)
  scan.run(opts, scan.cancel)
end

-- --- triggers ----------------------------------------------------------------

local function stop(timer)
  if timer then
    timer:stop()
    timer:close()
  end
  return nil
end

local function schedule_scan(opts)
  debounce_timer = stop(debounce_timer)
  debounce_timer = vim.uv.new_timer()
  debounce_timer:start(state.config().scan.debounce_ms, 0, function()
    debounce_timer = stop(debounce_timer)
    vim.schedule(function()
      M.scan(opts)
    end)
  end)
end

local function arm_sweep()
  sweep_timer = stop(sweep_timer)
  local cfg = state.config()
  local trigger = cfg.scan.trigger
  if trigger ~= 'interval' and trigger ~= 'on_save_and_interval' then
    return
  end
  local period = cfg.scan.interval_minutes * 60000
  sweep_timer = vim.uv.new_timer()
  sweep_timer:start(period, period, function()
    vim.schedule(function()
      M.scan({ kind = 'workspace', reason = 'periodic sweep' })
    end)
  end)
end

--- Never let gandalf's own output re-trigger gandalf.
local function scannable(rel)
  if not rel or rel:match('^%.git/') or rel:match('^reports/') then
    return false
  end
  return not vim.fs.basename(rel):match('^%.gandalf%-')
end

local function on_save(event)
  local cfg = state.config()
  local trigger = cfg.scan.trigger
  if not cfg.enabled or (trigger ~= 'on_save' and trigger ~= 'on_save_and_interval') then
    return
  end
  local rel = vim.fs.relpath(M.root(), vim.fs.normalize(event.match))
  if not scannable(rel) then
    return
  end
  schedule_scan({ kind = 'file', rel_path = rel, reason = 'saved ' .. rel })
end

local function attach_autocmds()
  local group = vim.api.nvim_create_augroup('gandalf', { clear = true })

  vim.api.nvim_create_autocmd('BufWritePost', { group = group, callback = on_save })

  -- A file opened after the scan still gets its squiggles.
  vim.api.nvim_create_autocmd('BufReadPost', {
    group = group,
    callback = function()
      if state.snapshot() then
        vim.schedule(function()
          ui.publish(state.findings(), state.config(), M.root())
        end)
      end
    end,
  })
end

-- --- setup -------------------------------------------------------------------

function M.setup(opts)
  local cfg = config.resolve(opts)
  state.set_config(cfg)
  if not cfg.enabled then
    ui.clear()
    return
  end
  attach_autocmds()
  arm_sweep()
  if cfg.scan.on_startup and cfg.scan.trigger ~= 'manual' then
    vim.defer_fn(function()
      M.scan({ kind = 'workspace', reason = 'startup' })
    end, STARTUP_DELAY_MS)
  end
end

return M
