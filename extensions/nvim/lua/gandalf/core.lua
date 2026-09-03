-- The ported logic: reading what gandalf says, with no reference to the editor.
--
-- gandalf is a Python CLI that runs ~30 gates and writes a JSON report. None of
-- that is reimplemented here. What is ported is what the VS Code extension had
-- to port too: the `--stream` event framing, the progress line gandalf draws on
-- stderr, and the score history it keeps in .gandalf-trend.jsonl.
--
-- One module per concern under `core/`, re-exported here: `gandalf.core` is the
-- spelling the specs and the rest of the plugin are written against, the same
-- way gandalf's own plugins.py re-exports toolrun, ignores and outcomes.
--
--   core/argv     the command line for one scan
--   core/levels   the severity ladder and the sort
--   core/fields   reading a value whatever key its tool used
--   core/findings one finding, and a gate's worth of them as rows
--   core/packages the dependency a finding names, and the one under the cursor
--   core/gates    the gates that assessed nothing
--   core/stream   the --stream events and the progress line
--   core/trend    score over time
--
-- No `vim.` calls: the whole of core/ is testable under plain Lua.

local argv = require('gandalf.core.argv')
local findings = require('gandalf.core.findings')
local gates = require('gandalf.core.gates')
local levels = require('gandalf.core.levels')
local packages = require('gandalf.core.packages')
local stream = require('gandalf.core.stream')
local trend = require('gandalf.core.trend')

local M = {}

-- the command line
M.scan_argv = argv.scan_argv

-- the severity ladder
M.LEVELS = levels.LEVELS
M.LEVEL_RANK = levels.LEVEL_RANK
M.LEVEL_LABEL = levels.LEVEL_LABEL
M.VERDICT_WORD = levels.VERDICT_WORD
M.sort_level = levels.sort_level
M.compare_findings = levels.compare_findings

-- reading a finding
M.read_finding = findings.read_finding
M.normalize_gate = findings.normalize_gate
M.normalize = findings.normalize

-- the dependency a finding is about
M.finding_package = packages.finding_package
M.package_at_cursor = packages.package_at_cursor
M.findings_for_package = packages.findings_for_package

-- gates that assessed nothing
M.gate_status = gates.gate_status
M.gates_by_status = gates.gates_by_status

-- --stream events and the progress line
M.event_parser = stream.event_parser
M.parse_progress = stream.parse_progress
M.progress_parser = stream.progress_parser
M.describe_progress = stream.describe_progress

-- score over time
M.parse_trend = trend.parse_trend
M.parse_log = trend.parse_log
M.sparkline = trend.sparkline
M.delta = trend.delta

return M
