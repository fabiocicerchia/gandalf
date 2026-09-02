-- Gates that assessed nothing.
--
-- gandalf answers "my tool isn't here" with an AMBER gate and a summary, which
-- looks exactly like a real warning. In a bare environment that is thirty-odd
-- rows of noise burying the findings that matter, so those gates are split out
-- and reported as what they are: never checked.

local M = {}

local BLOCKED = {
  'unavailable',
  'did not run',
  'timed out',
  'not found',
  'not installed',
  'not verified locally',
}
local INAPPLICABLE = { 'skipped', 'no target', 'no request', 'nothing in scope', 'no database' }

local function matches_any(text, patterns)
  local lower = text:lower()
  for _, pattern in ipairs(patterns) do
    if lower:find(pattern, 1, true) then
      return true
    end
  end
  return false
end

---@return 'reported'|'blocked'|'inapplicable'
function M.gate_status(gate)
  -- A red gate is always shown, whatever its summary says.
  if #(gate.findings or {}) > 0 or gate.outcome ~= 'warn' then
    return 'reported'
  end
  local summary = gate.summary or ''
  if matches_any(summary, BLOCKED) then
    return 'blocked'
  end
  if matches_any(summary, INAPPLICABLE) then
    return 'inapplicable'
  end
  return 'reported'
end

--- Split out the gates that assessed nothing, so "green" never quietly means
--- "never checked".
function M.gates_by_status(payload)
  local blocked, inapplicable = {}, {}
  for _, gate in ipairs(payload.gates or {}) do
    local status = M.gate_status(gate)
    if status == 'blocked' then
      blocked[#blocked + 1] = gate.name
    elseif status == 'inapplicable' then
      inapplicable[#inapplicable + 1] = gate.name
    end
  end
  return blocked, inapplicable
end

return M
