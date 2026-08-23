-- User commands only.
--
-- Deliberately cheap: nothing here requires core.lua, so a session that never
-- runs a scan never loads the plugin.

if vim.g.loaded_gandalf then
  return
end
vim.g.loaded_gandalf = true

--- setup() is optional: a command used before it runs gets the defaults rather
--- than an error about a nil config.
local function ready()
  local gandalf = require('gandalf')
  if not gandalf.is_setup() then
    gandalf.setup({})
  end
  return gandalf
end

local command = vim.api.nvim_create_user_command

command('GandalfScan', function()
  ready().scan({ kind = 'workspace', manual = true, reason = 'command' })
end, { desc = 'Gandalf: scan the workspace' })

command('GandalfScanFile', function()
  local gandalf = ready()
  local path = vim.fs.normalize(vim.api.nvim_buf_get_name(0))
  local rel = path ~= '' and vim.fs.relpath(gandalf.root(), path) or nil
  if not rel then
    return vim.notify('Gandalf: open a file inside the project first.', vim.log.levels.WARN)
  end
  gandalf.scan({ kind = 'file', rel_path = rel, manual = true, reason = 'command' })
end, { desc = 'Gandalf: scan the current file' })

command('GandalfReport', function()
  ready().report()
end, { desc = 'Gandalf: open the scorecard' })

command('GandalfReportLlm', function()
  ready().scan({
    kind = 'workspace',
    manual = true,
    llm = true,
    reason = 'report + LLM summary',
    on_done = function(ok)
      if ok then
        require('gandalf').report()
      end
    end,
  })
end, { desc = 'Gandalf: rescan with the LLM summary, then open the scorecard' })

command('GandalfList', function()
  ready().list()
end, { desc = 'Gandalf: every finding, in the quickfix list' })

command('GandalfFilter', function()
  ready().filter()
end, { desc = 'Gandalf: findings at one level, in the quickfix list' })

command('GandalfTimings', function()
  ready().timings()
end, { desc = 'Gandalf: per-gate timings, slowest first' })

command('GandalfHistory', function()
  ready().history()
end, { desc = 'Gandalf: score over time' })

command('GandalfCancel', function()
  ready().cancel()
end, { desc = 'Gandalf: cancel the running scan' })

command('GandalfLog', function()
  ready().show_log()
end, { desc = 'Gandalf: show the log' })
