-- Reading one finding, and turning a gate's worth of them into rows.
--
-- Reconciling each tool's finding shape is NOT here, and that is the point.
-- gandalf normalises its own findings (see gandalf/findings.py) and publishes
-- the result on every finding under `_gandalf`, so this reads one shape rather
-- than carrying a copy of six key lists that would drift from the Python ones.

local fields = require('gandalf.core.fields')
local gates = require('gandalf.core.gates')
local levels = require('gandalf.core.levels')
local packages = require('gandalf.core.packages')

local M = {}

--- The `_gandalf` block, when this build of gandalf emits one.
local function normalised(raw)
  local block = type(raw) == 'table' and raw._gandalf or nil
  if type(block) ~= 'table' then
    return nil
  end
  local function str(key)
    return type(block[key]) == 'string' and block[key] or ''
  end
  local function num(key)
    return type(block[key]) == 'number' and block[key] > 0 and block[key] or 0
  end
  return {
    path = str('path'),
    line = num('line'),
    column = num('column'),
    rule = str('rule'),
    message = str('message'),
    severity = str('severity'),
    url = str('url'),
  }
end

-- A gandalf older than findings.py sends no block. It still has to produce a
-- usable pane, so these are the keys gandalf's own report has always read --
-- deliberately not the full reconciliation, which is no longer this plugin's
-- job to carry.
local LEGACY_PATH = { 'path', 'filename', 'file', 'file_path' }
local LEGACY_LINE = { 'line', 'line_number', 'Line' }
local LEGACY_RULE = { 'rule_id', 'check_id', 'RuleID', 'test_id', 'code', 'id', 'rule' }
local LEGACY_MESSAGE = { 'message', 'issue_text', 'description', 'Description', 'error', 'finding' }
local LEGACY_SEVERITY = { 'severity', 'Severity', 'issue_severity', 'level', 'Level' }
local LEGACY_URL = { 'url', 'URL', 'PrimaryURL', 'help_uri' }

local function legacy(raw)
  return {
    path = fields.first_string(raw, LEGACY_PATH),
    line = fields.first_number(raw, LEGACY_LINE),
    column = 0,
    rule = fields.first_string(raw, LEGACY_RULE),
    message = fields.first_string(raw, LEGACY_MESSAGE),
    severity = fields.first_string(raw, LEGACY_SEVERITY):lower(),
    url = fields.first_string(raw, LEGACY_URL),
  }
end

--- What gandalf decided about a finding, or our best effort for an older build.
function M.read_finding(raw)
  if type(raw) ~= 'table' then
    return { path = '', line = 0, column = 0, rule = '', message = tostring(raw), severity = '', url = '' }
  end
  return normalised(raw) or legacy(raw)
end

--- One finding, as a row the editor can place.
local function finding_row(gate, category, raw)
  local n = M.read_finding(raw)
  local level = levels.GANDALF_LEVEL[n.severity] or 'unrated'
  return {
    gate = gate.name,
    category = category,
    outcome = gate.outcome,
    level = level,
    -- A level we place on the ladder is worth showing; one we don't isn't.
    severity_label = level ~= 'unrated' and n.severity:upper() or '',
    rule = n.rule,
    -- Nothing recognizable at all: show the raw record rather than a blank row.
    message = n.message ~= '' and n.message or '(no message)',
    path = n.path,
    line = n.line,
    column = n.column,
    url = n.url,
    package = packages.finding_package(raw),
    installed = fields.first_string(type(raw) == 'table' and raw or {}, packages.INSTALLED_KEYS),
    fixed = packages.fixed_version(raw),
  }
end

--- A gate that failed without structured findings still has to be visible --
--- its summary is the whole story (a build error, a failing test suite).
local function summary_row(gate, category)
  return {
    gate = gate.name,
    category = category,
    outcome = gate.outcome,
    level = 'unrated',
    severity_label = '',
    rule = '',
    message = gate.summary ~= '' and gate.summary or gate.name,
    path = '',
    line = 0,
    column = 0,
    url = '',
    package = '',
    installed = '',
    fixed = '',
  }
end

--- One gate's findings, as rows the editor can place.
function M.normalize_gate(gate)
  local out = {}
  local category = gate.category or 'Other'

  for _, raw in ipairs(gate.findings or {}) do
    out[#out + 1] = finding_row(gate, category, raw)
  end
  if #out == 0 and gate.outcome ~= 'pass' and gates.gate_status(gate) == 'reported' then
    out[1] = summary_row(gate, category)
  end
  return out
end

--- Every gate's findings, worst first.
function M.normalize(payload)
  local out = {}
  for _, gate in ipairs(payload.gates or {}) do
    for _, finding in ipairs(M.normalize_gate(gate)) do
      out[#out + 1] = finding
    end
  end
  table.sort(out, levels.compare_findings)
  return out
end

return M
