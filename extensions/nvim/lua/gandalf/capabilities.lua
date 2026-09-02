-- What the gandalf build on this machine actually accepts.
--
-- The plugin passed every optional flag unconditionally, so an older gandalf
-- failed the scan outright rather than running without them: argparse rejects
-- an unknown flag with exit 2. `--help` is the only thing that can answer this,
-- and it costs a process, so it is asked once per command and remembered.
--
-- This lives outside core/ because it runs a process; core/ stays `vim.`-free.

local M = {}

local HELP_TIMEOUT_MS = 5000

--- Keyed by the joined command, so a `cmd` changed through setup() re-probes
--- instead of inheriting the previous build's answer.
local cache = {}

--- The long flags `cmd` named in its own `--help`.
---
--- Returns nil when the probe could not run at all — a missing binary, a
--- timeout, a non-zero exit. Callers read nil as "unknown" and gate nothing,
--- which is exactly what this plugin did before the probe existed: a wrong
--- guess must not be worse than no guess.
---@param cmd string[]
---@return table<string, boolean>|nil
function M.of(cmd)
  local key = table.concat(cmd, ' ')
  local remembered = cache[key]
  if remembered ~= nil then
    return remembered.flags
  end

  local ok, out = pcall(function()
    local full = vim.list_extend(vim.list_slice(cmd, 1, #cmd), { '--help' })
    return vim.system(full, { text = true }):wait(HELP_TIMEOUT_MS)
  end)

  local flags = nil
  if ok and out and out.code == 0 then
    -- argparse prints usage to stdout, but a build that errors early may put it
    -- on stderr; read both rather than depend on which.
    local help = (out.stdout or '') .. (out.stderr or '')
    flags = {}
    for flag in help:gmatch('%-%-[%w][%w-]*') do
      flags[flag] = true
    end
  end

  cache[key] = { flags = flags }
  return flags
end

--- Forget every probe, so the next scan asks again. For tests and for a user
--- who has just upgraded gandalf without restarting Neovim.
function M.reset()
  cache = {}
end

return M
