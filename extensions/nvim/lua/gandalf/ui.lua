-- Diagnostics, the scorecard float, and the quickfix list.

local core = require('gandalf.core')

local M = {}

local NS = vim.api.nvim_create_namespace('gandalf')
M.namespace = NS

--- Findings are keyed by repo-relative path; a diagnostic needs a buffer.
--- Files that are not open keep their findings in the report and get their
--- squiggles when they are opened.
local function loaded_buffers()
  local out = {}
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_loaded(buf) then
      local name = vim.api.nvim_buf_get_name(buf)
      if name ~= '' then
        out[vim.fs.normalize(name)] = buf
      end
    end
  end
  return out
end

--- What a squiggle should say beyond the message: which gate produced it, and
--- everything that gate knew about it.
local function facts_of(finding)
  local facts = { 'gate: ' .. finding.gate, 'category: ' .. finding.category }
  if finding.severity_label ~= '' then
    facts[#facts + 1] = 'severity: ' .. finding.severity_label
  end
  if finding.rule ~= '' then
    facts[#facts + 1] = 'rule: ' .. finding.rule
  end
  return facts
end

--- The editor clamps `end_col`, so the whole line is covered without having to
--- read the buffer to measure it.
local FULL_LINE = 9999

local function diagnostic_of(finding, severity)
  return {
    lnum = math.max(0, finding.line - 1),
    col = math.max(0, finding.column - 1),
    end_lnum = math.max(0, finding.line - 1),
    end_col = FULL_LINE,
    severity = severity,
    source = 'gandalf',
    code = finding.rule ~= '' and finding.rule or finding.gate,
    message = finding.message .. '\n\n' .. table.concat(facts_of(finding), ' · '),
  }
end

--- Whether this finding earns a squiggle at all: it needs somewhere to go, a
--- severity the configuration maps it to, and a level at or above the floor.
local function publishable(finding, cfg, floor)
  if finding.path == '' or finding.line <= 0 then
    return nil
  end
  local severity = cfg.diagnostics.severity[finding.level]
  if not severity or core.LEVEL_RANK[core.sort_level(finding)] > floor then
    return nil
  end
  return severity
end

--- Publish everything at once. A partial publish is not an option: the
--- namespace is global, so writing only what was just scanned would drop
--- everything else.
function M.publish(findings, cfg, root)
  vim.diagnostic.reset(NS)
  if not cfg.diagnostics.enabled then
    return
  end

  local buffers = loaded_buffers()
  local floor = core.LEVEL_RANK[cfg.diagnostics.min_level] or 99
  local by_buf = {}

  for _, finding in ipairs(findings) do
    local severity = publishable(finding, cfg, floor)
    local buf = severity and buffers[vim.fs.normalize(vim.fs.joinpath(root, finding.path))]
    if buf then
      local list = by_buf[buf] or {}
      -- A backstop against a pathological file, not something worth tuning.
      if #list < cfg.diagnostics.max_per_file then
        list[#list + 1] = diagnostic_of(finding, severity)
        by_buf[buf] = list
      end
    end
  end

  for buf, list in pairs(by_buf) do
    vim.diagnostic.set(NS, buf, list)
  end
end

function M.clear()
  vim.diagnostic.reset(NS)
end

-- --- floats ------------------------------------------------------------------

function M.float(lines, opts)
  opts = opts or {}
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].modifiable = false
  vim.bo[buf].filetype = opts.filetype or 'markdown'
  vim.bo[buf].bufhidden = 'wipe'

  local width = 0
  for _, line in ipairs(lines) do
    width = math.max(width, vim.fn.strdisplaywidth(line))
  end
  width = math.min(math.max(width + 2, 48), math.floor(vim.o.columns * 0.9))
  local height = math.min(math.max(#lines, 3), math.floor(vim.o.lines * 0.8))

  local win = vim.api.nvim_open_win(buf, true, {
    relative = 'editor',
    row = math.floor((vim.o.lines - height) / 2),
    col = math.floor((vim.o.columns - width) / 2),
    width = width,
    height = height,
    style = 'minimal',
    border = 'rounded',
    title = opts.title or ' Gandalf ',
    title_pos = 'center',
  })
  vim.wo[win].wrap = false
  vim.wo[win].cursorline = true
  for _, key in ipairs({ 'q', '<Esc>' }) do
    vim.keymap.set('n', key, function()
      if vim.api.nvim_win_is_valid(win) then
        vim.api.nvim_win_close(win, true)
      end
    end, { buffer = buf, nowait = true, silent = true })
  end
  return buf, win
end

local MARK = { pass = '●', warn = '●', fail = '●' }

--- The gates that reported something, grouped as the report groups them and in
--- the order the report listed them.
local function category_lines(payload)
  local by_category, order = {}, {}
  for _, gate in ipairs(payload.gates or {}) do
    local category = gate.category or 'Other'
    if not by_category[category] then
      by_category[category] = {}
      order[#order + 1] = category
    end
    table.insert(by_category[category], gate)
  end

  local lines = {}
  for _, category in ipairs(order) do
    lines[#lines + 1] = category
    for _, gate in ipairs(by_category[category]) do
      if core.gate_status(gate) == 'reported' then
        lines[#lines + 1] =
          string.format('  %s %-22s %s', MARK[gate.outcome] or '?', gate.name, gate.summary or '')
      end
    end
    lines[#lines + 1] = ''
  end
  return lines
end

--- What could not run, and what had nothing to do -- kept apart, because a
--- green board must never quietly mean "never checked".
local function unassessed_lines(snapshot)
  local lines = {}
  if #snapshot.blocked > 0 then
    lines[#lines + 1] = 'Could not run (install the tool, or build the image):'
    lines[#lines + 1] = '  ' .. table.concat(snapshot.blocked, ', ')
    lines[#lines + 1] = ''
  end
  if #snapshot.inapplicable > 0 then
    lines[#lines + 1] = 'Nothing to assess: ' .. table.concat(snapshot.inapplicable, ', ')
    lines[#lines + 1] = ''
  end
  return lines
end

--- The scorecard, as gandalf's own terminal output reads: verdict and score,
--- then gates by category, then what could not run.
function M.report_lines(snapshot)
  local payload = snapshot.payload
  local lines = {
    string.format('%s · %d/100    scope: %s', core.VERDICT_WORD[payload.verdict] or '?', payload.score or 0, payload.scope or '?'),
    string.rep('─', 60),
    '',
  }

  for _, line in ipairs(category_lines(payload)) do
    lines[#lines + 1] = line
  end
  for _, line in ipairs(unassessed_lines(snapshot)) do
    lines[#lines + 1] = line
  end

  lines[#lines + 1] = string.format('%d finding(s)', #snapshot.findings)
  if payload.summary and payload.summary ~= '' then
    lines[#lines + 1] = ''
    for line in tostring(payload.summary):gmatch('[^\n]+') do
      lines[#lines + 1] = line
    end
  end
  return lines
end

--- Nothing was found -- and whether that is worth anything. A gate whose tool
--- is missing reports AMBER and moves on, so an empty hover can mean "clean" or
--- "never checked", and those are not the same answer.
local function nothing_found_lines(snapshot)
  local lines = { 'No findings against this dependency.' }
  local blocked = snapshot and snapshot.blocked or {}
  if #blocked > 0 then
    lines[#lines + 1] = ''
    lines[#lines + 1] =
      string.format('⚠ %d gate(s) could not run, so this is not proof of anything:', #blocked)
    lines[#lines + 1] = '  ' .. table.concat(blocked, ', ')
    lines[#lines + 1] = '  Run :checkhealth gandalf, or :GandalfLog.'
  end
  return lines
end

--- One block per finding: a headline, the message indented under it, and the
--- two things a reader will act on -- the fix and the advisory.
local function finding_lines(findings)
  local lines = { string.format('%d finding(s)', #findings), '' }
  for _, finding in ipairs(findings) do
    local head = { MARK[finding.outcome] or '?' }
    if finding.severity_label ~= '' then
      head[#head + 1] = finding.severity_label
    end
    head[#head + 1] = finding.gate
    if finding.rule ~= '' then
      head[#head + 1] = '· ' .. finding.rule
    end
    lines[#lines + 1] = table.concat(head, ' ')
    for line in finding.message:gmatch('[^\n]+') do
      lines[#lines + 1] = '    ' .. line
    end
    if finding.fixed ~= '' then
      lines[#lines + 1] = '    fixed in: ' .. finding.fixed
    end
    if finding.url ~= '' then
      lines[#lines + 1] = '    ' .. finding.url
    end
    lines[#lines + 1] = ''
  end
  return lines
end

--- Everything gandalf knows about one dependency: a heading, then either the
--- findings or the case for not trusting their absence.
function M.hover_lines(package, findings, snapshot)
  local installed = ''
  for _, finding in ipairs(findings) do
    if finding.installed ~= '' then
      installed = finding.installed
      break
    end
  end

  local lines = {
    installed ~= '' and (package .. '  ' .. installed) or package,
    string.rep('─', math.max(#package + 12, 40)),
    '',
  }

  local rest = #findings == 0 and nothing_found_lines(snapshot) or finding_lines(findings)
  for _, line in ipairs(rest) do
    lines[#lines + 1] = line
  end
  return lines
end

--- Findings into the quickfix list, which is where a list of places to go
--- belongs in this editor.
function M.to_quickfix(findings, root, title)
  local items = {}
  for _, finding in ipairs(findings) do
    items[#items + 1] = {
      filename = finding.path ~= '' and vim.fs.joinpath(root, finding.path) or nil,
      lnum = math.max(1, finding.line),
      col = math.max(1, finding.column),
      text = string.format(
        '[%s] %s%s',
        finding.gate,
        finding.rule ~= '' and (finding.rule .. ': ') or '',
        finding.message:gsub('\n', ' ')
      ),
      type = (finding.level == 'critical' or finding.level == 'high') and 'E' or 'W',
    }
  end
  vim.fn.setqflist({}, ' ', { title = title, items = items })
end

return M
