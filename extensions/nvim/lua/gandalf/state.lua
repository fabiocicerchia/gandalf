-- What the plugin knows right now: the configuration, the last completed run,
-- the run in flight, and the log.
--
-- One module rather than upvalues in init.lua, because the scan runner, the
-- commands and the status line all read the same four things and only the
-- runner writes them.

local core = require('gandalf.core')

local M = {}

--- Lines kept in the in-memory log before the oldest is dropped.
local LOG_LINES_KEPT = 500

local cfg = nil
--- The last completed run.
local snapshot = nil
--- Gates reported by the run in flight, keyed by name, so the list fills
--- during a scan instead of at the end of it.
local streaming = nil
local handle = nil
local progress = nil
local log_lines = {}

function M.log(fmt, ...)
  log_lines[#log_lines + 1] = string.format('[%s] ' .. fmt, os.date('%H:%M:%S'), ...)
  if #log_lines > LOG_LINES_KEPT then
    table.remove(log_lines, 1)
  end
end

function M.log_text()
  return log_lines
end

function M.notify(msg, level)
  vim.notify('Gandalf: ' .. msg, level or vim.log.levels.INFO)
end

-- --- the configuration -------------------------------------------------------

function M.config()
  return cfg
end

function M.set_config(value)
  cfg = value
end

function M.is_setup()
  return cfg ~= nil
end

-- --- the run in flight -------------------------------------------------------

function M.is_scanning()
  return handle ~= nil
end

function M.handle()
  return handle
end

function M.begin(started)
  handle = started
  progress = nil
end

--- Streaming starts before the process does: a gate can land on the very first
--- chunk of stdout.
function M.begin_stream()
  streaming = {}
end

--- Record a streamed gate, unless the run it belongs to is already over.
function M.push_stream(name, findings)
  if not streaming then
    return false
  end
  streaming[name] = findings
  return true
end

function M.set_progress(state)
  progress = state
end

function M.progress()
  return progress
end

--- The run is over, however it ended: the report (or the failure) is now the
--- whole truth, so the partials go.
function M.finish()
  handle = nil
  streaming = nil
  progress = nil
end

-- --- the last completed run --------------------------------------------------

function M.snapshot()
  return snapshot
end

function M.set_snapshot(value)
  snapshot = value
end

--- Findings from the completed run, with anything the run in flight has
--- already superseded.
function M.findings()
  local out = {}
  local replaced = {}
  if streaming then
    for gate, findings in pairs(streaming) do
      replaced[gate] = true
      for _, finding in ipairs(findings) do
        out[#out + 1] = finding
      end
    end
  end
  for _, finding in ipairs(snapshot and snapshot.findings or {}) do
    if not replaced[finding.gate] then
      out[#out + 1] = finding
    end
  end
  table.sort(out, core.compare_findings)
  return out
end

--- A lualine component, or anything else that wants one string.
function M.statusline()
  if not cfg then
    return ''
  end
  if handle then
    return progress and ('gandalf ' .. core.describe_progress(progress)) or 'gandalf scanning'
  end
  if not snapshot then
    return ''
  end
  return string.format(
    'gandalf %s %d/100',
    core.VERDICT_WORD[snapshot.payload.verdict] or '?',
    snapshot.payload.score or 0
  )
end

return M
