-- The severity ladder: the order everything is shown and filtered in.

local M = {}

--- Worst first: the pane's order and the filter's order.
M.LEVELS = { 'critical', 'high', 'medium', 'low', 'info', 'unrated' }

M.LEVEL_RANK = { critical = 1, high = 2, medium = 3, low = 4, info = 5, unrated = 6 }

M.LEVEL_LABEL = {
  critical = 'Critical',
  high = 'High',
  medium = 'Medium',
  low = 'Low',
  info = 'Info',
  unrated = 'Unrated',
}

M.VERDICT_WORD = { pass = 'GREEN', warn = 'AMBER', fail = 'RED' }

--- gandalf's normalized severity -> the ladder shown here. `unknown` is the
--- tool saying it declined to rate the finding, which is what `unrated` means;
--- `''` (no severity field at all) lands there too and inherits its gate's
--- outcome instead.
M.GANDALF_LEVEL = {
  critical = 'critical',
  high = 'high',
  medium = 'medium',
  low = 'low',
  info = 'info',
  unknown = 'unrated',
}

--- Where an unrated finding sorts. Its gate's outcome is the only signal there
--- is, and a failing gate's finding belongs above a tool's LOW -- a red mypy
--- error must not sink below a cosmetic advisory just because mypy names no
--- severity.
local IMPLIED_LEVEL = { fail = 'high', warn = 'medium', pass = 'info' }

function M.sort_level(finding)
  if finding.level == 'unrated' then
    return IMPLIED_LEVEL[finding.outcome] or 'info'
  end
  return finding.level
end

--- Worst reported level, then gate, then file, then line.
function M.compare_findings(a, b)
  local ra = M.LEVEL_RANK[M.sort_level(a)]
  local rb = M.LEVEL_RANK[M.sort_level(b)]
  if ra ~= rb then
    return ra < rb
  end
  -- Tie on effective rank: a level the tool actually stated outranks one
  -- inferred from the gate's outcome.
  local ua = a.level == 'unrated' and 1 or 0
  local ub = b.level == 'unrated' and 1 or 0
  if ua ~= ub then
    return ua < ub
  end
  if a.gate ~= b.gate then
    return a.gate < b.gate
  end
  if a.path ~= b.path then
    return a.path < b.path
  end
  return a.line < b.line
end

return M
