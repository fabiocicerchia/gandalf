-- The ported logic: reading what gandalf says, with no reference to the editor.
--
-- gandalf is a Python CLI that runs ~30 gates and writes a JSON report. None of
-- that is reimplemented here. What is ported is what the VS Code extension had
-- to port too: the `--stream` event framing, the progress line gandalf draws on
-- stderr, and the score history it keeps in .gandalf-trend.jsonl.
--
-- Reconciling each tool's finding shape is NOT here, and that is the point.
-- gandalf normalises its own findings (see gandalf/findings.py) and publishes
-- the result on every finding under `_gandalf`, so this reads one shape rather
-- than carrying a copy of six key lists that would drift from the Python ones.
--
-- No `vim.` calls: the whole module is testable under plain Lua.

local M = {}

-- --- the command line --------------------------------------------------------

--- Argv for one scan.
---@param cfg table resolved configuration
---@param opts table { kind = 'workspace'|'file'|'commit', rel_path?, commit? }
function M.scan_argv(cfg, opts)
  local argv = {}
  local function add(...)
    for _, value in ipairs({ ... }) do
      argv[#argv + 1] = value
    end
  end

  if opts.kind == 'file' and opts.rel_path then
    add('--path', (opts.rel_path:gsub('\\', '/')))
  elseif opts.kind == 'commit' and opts.commit then
    add('--commit', opts.commit)
  end

  if not (opts.llm or cfg.scan.llm) then
    add('--no-llm')
  end
  -- A one-file scorecard is not a report anyone wants, and the HTML is not
  -- rendered here in any case.
  add('--no-html')
  if opts.out_dir then
    add('--out-dir', opts.out_dir)
  end
  -- Editor scans stay out of the trend log: it is meant to be per commit, and a
  -- scan per save would swamp it. Scanning a named commit is the exception --
  -- that is exactly one entry for exactly one commit, which is what the log is.
  if opts.kind ~= 'commit' then
    add('--no-trend')
  end
  if cfg.config_path and cfg.config_path ~= '' then
    add('--config', cfg.config_path)
  end
  if cfg.scan.concurrency > 0 then
    add('--concurrency', tostring(cfg.scan.concurrency))
  end
  -- The cache is keyed per gate on a hash of the whole scanned file set, so a
  -- one-file scan would overwrite the workspace entries with a one-file hash
  -- and make the next full scan a complete miss.
  if cfg.scan.use_cache and opts.kind == 'workspace' then
    add('--cache')
  end
  if opts.stream then
    add('--stream')
  end
  for _, pattern in ipairs(cfg.exclude) do
    add('--exclude', pattern)
  end
  for _, extra in ipairs(cfg.extra_args) do
    add(extra)
  end
  return argv
end

-- --- the severity ladder -----------------------------------------------------

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
local GANDALF_LEVEL = {
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

-- --- reading a finding -------------------------------------------------------

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

local function first_string(raw, keys)
  for _, key in ipairs(keys) do
    local value = raw[key]
    if type(value) == 'string' and value:match('%S') then
      return (value:gsub('^%s+', ''):gsub('%s+$', ''))
    end
    if type(value) == 'number' then
      return tostring(value)
    end
  end
  return ''
end

local function first_number(raw, keys)
  for _, key in ipairs(keys) do
    local value = raw[key]
    if type(value) == 'number' and value > 0 then
      return math.floor(value)
    end
    if type(value) == 'string' and value:match('^%d+$') and tonumber(value) > 0 then
      return tonumber(value)
    end
  end
  return 0
end

local function legacy(raw)
  return {
    path = first_string(raw, LEGACY_PATH),
    line = first_number(raw, LEGACY_LINE),
    column = 0,
    rule = first_string(raw, LEGACY_RULE),
    message = first_string(raw, LEGACY_MESSAGE),
    severity = first_string(raw, LEGACY_SEVERITY):lower(),
    url = first_string(raw, { 'url', 'URL', 'PrimaryURL', 'help_uri' }),
  }
end

--- What gandalf decided about a finding, or our best effort for an older build.
function M.read_finding(raw)
  if type(raw) ~= 'table' then
    return { path = '', line = 0, column = 0, rule = '', message = tostring(raw), severity = '', url = '' }
  end
  return normalised(raw) or legacy(raw)
end

-- What a tool calls the package a finding is about. gandalf leaves every gate's
-- own keys on the finding alongside the `_gandalf` block, so this reads them
-- directly rather than asking for a new normalized field.
--
-- Deliberately not a bare `name`: on a checkov or semgrep finding that is the
-- rule, and hovering a package only to be told about an unrelated rule is worse
-- than being told nothing.
local PACKAGE_KEYS = { 'PkgName', 'pkg_name', 'PackageName', 'package_name', 'packageName' }
local INSTALLED_KEYS = { 'InstalledVersion', 'installed_version', 'version', 'Version' }
local FIXED_KEYS = { 'FixedVersion', 'fixed_version', 'fixed' }

--- The package a finding names, or ''. Several shapes, because the gates pass
--- their tool's output through untouched: trivy says `PkgName`, osv-scanner
--- nests it under `affected[].package.name`, others use a `package` object.
function M.finding_package(raw)
  if type(raw) ~= 'table' then
    return ''
  end
  local direct = first_string(raw, PACKAGE_KEYS)
  if direct ~= '' then
    return direct
  end
  local pkg = raw.package
  if type(pkg) == 'string' and pkg ~= '' then
    return pkg
  end
  if type(pkg) == 'table' and type(pkg.name) == 'string' then
    return pkg.name
  end
  local affected = raw.affected
  if type(affected) == 'table' and type(affected[1]) == 'table' then
    local nested = affected[1].package
    if type(nested) == 'table' and type(nested.name) == 'string' then
      return nested.name
    end
  end
  -- trivy's PkgID is `name@version`; the name half is still the answer.
  if type(raw.PkgID) == 'string' then
    return raw.PkgID:match('^(.+)@[^@]*$') or ''
  end
  return ''
end

--- `fix_versions` is a list in pip-audit and a string everywhere else.
local function fixed_version(raw)
  if type(raw) ~= 'table' then
    return ''
  end
  local list = raw.fix_versions
  if type(list) == 'table' and type(list[1]) == 'string' then
    return table.concat(list, ', ')
  end
  return first_string(raw, FIXED_KEYS)
end

--- One gate's findings, as rows the editor can place.
function M.normalize_gate(gate)
  local out = {}
  local category = gate.category or 'Other'

  for _, raw in ipairs(gate.findings or {}) do
    local n = M.read_finding(raw)
    local level = GANDALF_LEVEL[n.severity] or 'unrated'
    out[#out + 1] = {
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
      package = M.finding_package(raw),
      installed = first_string(type(raw) == 'table' and raw or {}, INSTALLED_KEYS),
      fixed = fixed_version(raw),
    }
  end

  -- A gate that failed without structured findings still has to be visible --
  -- its summary is the whole story (a build error, a failing test suite).
  if #out == 0 and gate.outcome ~= 'pass' and M.gate_status(gate) == 'reported' then
    out[1] = {
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
  return out
end

--- The dependency named on a manifest line, or ''.
---
--- Pattern-based rather than per-format on purpose: five shapes cover
--- requirements.txt, package.json, go.mod, Cargo.toml, pyproject.toml and
--- Gemfile between them, and a manifest nobody thought of still has a chance.
--- Order matters — a quoted requirement is checked before a bare `key =`, or
--- `dependencies = ["flask>=2"]` would answer "dependencies".
function M.package_at_cursor(line)
  local s = (line or ''):gsub('^%s+', ''):gsub('%s+$', '')
  -- Comments, section headers and pip's flag lines name no dependency.
  if s == '' or s:match('^[#;]') or s:match('^//') or s:match('^%[%[?%a') or s:match('^%-') then
    return ''
  end
  -- `flask[async]==2.0` is an ordinary requirements.txt line, and the extras
  -- sit exactly where the version operator is looked for. Only a bracket whose
  -- contents are extras-shaped is dropped, so Cargo's `features = ["full"]`
  -- (bracket not glued to a name, quotes inside) is left alone.
  s = s:gsub('([%a][%w%._%-]*)%[[%w%s,%._%-]*%]', '%1')
  return s:match("^gem%s+['\"]([^'\"]+)") -- Gemfile
    or s:match('^"([^"]+)"%s*:') -- package.json, and any JSON manifest
    or s:match("['\"]%s*([%a][%w%._%-]*)%s*[><=~!^]") -- "flask>=2" in a list
    or s:match('^([%w%._%-/]+)%s+v%d') -- go.mod
    or s:match('^([%a@][%w%._%-/]*)%s*[=~<>!]') -- serde = "1", flask==2.0
    or s:match('^([%a][%w%._%-]*)$') -- a bare requirements.txt line
    or ''
end

--- Findings that name `package`. Case-insensitive: tools disagree on the case
--- of a package name far more often than two real packages differ only by it.
function M.findings_for_package(findings, package)
  local want = package:lower()
  local out = {}
  for _, finding in ipairs(findings or {}) do
    if (finding.package or '') ~= '' and finding.package:lower() == want then
      out[#out + 1] = finding
    end
  end
  return out
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

function M.normalize(payload)
  local out = {}
  for _, gate in ipairs(payload.gates or {}) do
    for _, finding in ipairs(M.normalize_gate(gate)) do
      out[#out + 1] = finding
    end
  end
  table.sort(out, M.compare_findings)
  return out
end

-- --- gates that assessed nothing ---------------------------------------------

-- gandalf answers "my tool isn't here" with an AMBER gate and a summary, which
-- looks exactly like a real warning. In a bare environment that is thirty-odd
-- rows of noise burying the findings that matter.
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

-- --- --stream events ---------------------------------------------------------
--
-- gandalf writes one NDJSON line per gate as it finishes. Without reading them
-- nothing reaches the user until the final report is written, so a pane sits
-- empty for the whole run. The aggregate still comes only from the report -- a
-- verdict and a composite score are properties of the whole run, and no single
-- gate result can produce them.
--
-- Event lines share stdout with the human scorecard, which is printed at the
-- end, so they are picked out by their prefix and everything else is handed
-- back untouched.

local EVENT_PREFIX = '{"event"'

local function is_outcome(value)
  return value == 'pass' or value == 'warn' or value == 'fail'
end

--- Validate rather than trust: a malformed line must not poison the pane.
local function to_event(parsed)
  if type(parsed) ~= 'table' then
    return nil
  end
  if parsed.event == 'start' then
    if type(parsed.gates) ~= 'number' then
      return nil
    end
    return { event = 'start', scope = tostring(parsed.scope or ''), gates = parsed.gates }
  end
  if parsed.event ~= 'gate' then
    return nil
  end
  if type(parsed.name) ~= 'string' or not is_outcome(parsed.outcome) then
    return nil
  end
  return {
    event = 'gate',
    index = type(parsed.index) == 'number' and parsed.index or 0,
    total = type(parsed.total) == 'number' and parsed.total or 0,
    name = parsed.name,
    outcome = parsed.outcome,
    score = type(parsed.score) == 'number' and parsed.score or 0,
    summary = type(parsed.summary) == 'string' and parsed.summary or '',
    findings = type(parsed.findings) == 'table' and parsed.findings or {},
    category = type(parsed.category) == 'string' and parsed.category or nil,
    duration = type(parsed.duration) == 'number' and parsed.duration or nil,
  }
end

--- A stdout reader that survives chunk boundaries.
---@param decode fun(text:string):any JSON decoder (vim.json.decode in the editor)
function M.event_parser(decode)
  local tail = ''
  return {
    --- @return table events, string text  -- the plain, non-event output
    feed = function(chunk)
      local events, text = {}, {}
      local buffer = tail .. (chunk or '')
      tail = buffer:match('([^\n]*)$') or ''
      buffer = buffer:sub(1, #buffer - #tail)
      for line in buffer:gmatch('([^\n]*)\n') do
        local trimmed = line:gsub('^%s+', '')
        if trimmed:sub(1, #EVENT_PREFIX) == EVENT_PREFIX then
          local ok, parsed = pcall(decode, trimmed)
          local event = ok and to_event(parsed) or nil
          if event then
            events[#events + 1] = event
          else
            -- Not an event after all, or truncated: keep it readable rather
            -- than failing a scan over it.
            text[#text + 1] = line
          end
        else
          text[#text + 1] = line
        end
      end
      return events, #text > 0 and (table.concat(text, '\n') .. '\n') or ''
    end,
    --- Whatever was left unterminated when the process exited.
    flush = function()
      local rest = tail
      tail = ''
      return rest
    end,
  }
end

-- --- the progress line -------------------------------------------------------
--
-- gandalf already reports what a run is doing: one self-overwriting line on
-- stderr, `\r ESC[K [2/3] Running 37 gates  [###...] 12/37 semgrep`, which
-- GANDALF_PROGRESS=1 turns on for a piped child. So there is nothing to guess
-- at -- that line is parsed.

local ANSI = '\27%[[0-9;]*[A-Za-z]'

--- One redraw -> a progress state, or nil when the segment is not one.
function M.parse_progress(raw)
  local line = (raw:gsub(ANSI, '')):gsub('%s+$', '')
  local index, total, rest = line:match('^%[(%d+)/(%d+)%]%s+(.*)$')
  if not index then
    return nil
  end
  index, total = tonumber(index), tonumber(total)
  if not total or total == 0 then
    return nil
  end

  local label, done, gates, gate = rest, 0, 0, ''
  local head, d, t, tail = rest:match('^(.-)%s*%[[^%]]*%]%s*(%d+)/(%d+)%s*(.*)$')
  if head then
    label = (head:gsub('%s+$', ''))
    done, gates, gate = tonumber(d), tonumber(t), (tail:gsub('%s+$', ''))
  end

  -- A stage counter of [2/3] means stage 2 has started, so 1 of 3 is behind us.
  -- Within the gate stage -- essentially the whole runtime -- the completed
  -- fraction fills the slice.
  local within = gates > 0 and (done / gates) or 0
  local percent = ((index - 1 + within) / total) * 100
  return {
    stage = label,
    stage_index = index,
    stage_total = total,
    gates_done = done,
    gates_total = gates,
    gate = gate,
    percent = math.max(0, math.min(100, percent)),
  }
end

--- A stderr reader. Redraws are separated by `\r` with no trailing newline, so
--- only delimited segments are parsed; anything that is not a progress line is
--- handed back as noise for the error path.
function M.progress_parser()
  local tail = ''
  return {
    ---@return table|nil progress, string noise
    feed = function(chunk)
      local buffer = tail .. (chunk or '')
      local segments = {}
      for segment in buffer:gmatch('([^\r\n]*)[\r\n]') do
        segments[#segments + 1] = segment
      end
      tail = buffer:match('([^\r\n]*)$') or ''

      local progress, noise = nil, {}
      for _, segment in ipairs(segments) do
        if segment:match('%S') then
          local parsed = M.parse_progress(segment)
          if parsed then
            progress = parsed
          else
            noise[#noise + 1] = (segment:gsub(ANSI, ''))
          end
        end
      end
      return progress, #noise > 0 and (table.concat(noise, '\n') .. '\n') or ''
    end,
    flush = function()
      local rest = tail
      tail = ''
      if rest:match('%S') and not M.parse_progress(rest) then
        return (rest:gsub(ANSI, '')) .. '\n'
      end
      return ''
    end,
  }
end

--- "gates 12/37 · semgrep", or the stage label outside the gate stage.
function M.describe_progress(p)
  if p.gates_total == 0 then
    return p.stage
  end
  local of = string.format('gates %d/%d', p.gates_done, p.gates_total)
  return p.gate ~= '' and (of .. ' · ' .. p.gate) or of
end

-- --- score over time ---------------------------------------------------------
--
-- Every CLI run appends a line to .gandalf-trend.jsonl -- commit, score,
-- timestamp. Joined against `git log` it answers the question a single
-- scorecard cannot: is this getting better?

--- The newest score per commit. The log is append-only, so a commit rescanned
--- later appears more than once and the last line wins.
function M.parse_trend(text, decode)
  local out = {}
  for line in (text .. '\n'):gmatch('([^\n]*)\n') do
    if line:match('^%s*{') then
      local ok, raw = pcall(decode, line)
      if ok and type(raw) == 'table' and type(raw.commit) == 'string' and type(raw.score) == 'number' then
        out[raw.commit] = { commit = raw.commit, score = raw.score, at = raw.generated_at or '' }
      end
    end
    -- A truncated final line is normal for an append-only log.
  end
  return out
end

--- `git log --format=%h%x1f%s%x1f%cs`, newest first.
function M.parse_log(stdout)
  local out = {}
  for line in (stdout .. '\n'):gmatch('([^\n]*)\n') do
    local short, subject, date = line:match('^([^\31]*)\31([^\31]*)\31([^\31]*)$')
    if short and short ~= '' then
      out[#out + 1] = { short = short, subject = subject, date = date }
    end
  end
  return out
end

local TICKS = { '\226\150\129', '\226\150\130', '\226\150\131', '\226\150\132', '\226\150\133', '\226\150\134', '\226\150\135', '\226\150\136' }

--- A score history as one line of text. Scaled across the observed range, not
--- 0-100: the interesting movement in a repository that sits in the eighties is
--- within those eighties.
function M.sparkline(scores)
  if #scores == 0 then
    return ''
  end
  local low, high = scores[1], scores[1]
  for _, score in ipairs(scores) do
    low = math.min(low, score)
    high = math.max(high, score)
  end
  local span = high - low
  local out = {}
  for i, score in ipairs(scores) do
    local tick = span == 0 and 1 or (math.floor(((score - low) / span) * (#TICKS - 1) + 0.5) + 1)
    out[i] = TICKS[tick]
  end
  return table.concat(out)
end

--- "+5", "-3", or "" for the first scored commit in the series.
function M.delta(score, previous)
  if previous == nil then
    return ''
  end
  local d = score - previous
  if d == 0 then
    return '±0'
  end
  return (d > 0 and '+' or '') .. tostring(d)
end

return M
