-- What the :Gandalf* commands do.
--
-- Each one needs a completed run to say anything, so each goes through
-- `ensure_scanned`: if nothing has been scanned yet, scan first and continue
-- only if that worked.

local core = require('gandalf.core')
local scan = require('gandalf.scan')
local state = require('gandalf.state')
local ui = require('gandalf.ui')

local M = {}

--- Commits `git log` is asked for when drawing the score history.
local HISTORY_COMMITS = 40

local function ensure_scanned(cb)
  if state.snapshot() then
    return cb()
  end
  state.notify('scanning…')
  scan.run({
    kind = 'workspace',
    manual = true,
    reason = 'report',
    on_done = function(ok)
      if ok then
        cb()
      end
    end,
  }, scan.cancel)
end

function M.report()
  ensure_scanned(function()
    ui.float(ui.report_lines(state.snapshot()), {
      title = ' Gandalf scorecard ',
      filetype = 'gandalf-report',
    })
  end)
end

--- Explain the dependency under the cursor: what gandalf found against it, and
--- what it could not check.
function M.hover()
  local package = core.package_at_cursor(vim.api.nvim_get_current_line())
  if package == '' then
    return state.notify('no dependency on this line.')
  end
  ensure_scanned(function()
    local matched = core.findings_for_package(state.findings(), package)
    ui.float(ui.hover_lines(package, matched, state.snapshot()), {
      title = ' ' .. package .. ' ',
      filetype = 'gandalf-hover',
    })
  end)
end

--- Every finding, in the quickfix list.
function M.list()
  ensure_scanned(function()
    local findings = state.findings()
    if #findings == 0 then
      return state.notify('nothing found.')
    end
    ui.to_quickfix(findings, scan.root(), 'Gandalf')
    vim.cmd('copen')
  end)
end

--- How many findings sit at each level, and which levels have any.
local function levels_present(findings)
  local counts = {}
  for _, finding in ipairs(findings) do
    counts[finding.level] = (counts[finding.level] or 0) + 1
  end
  local present = {}
  for _, level in ipairs(core.LEVELS) do
    if (counts[level] or 0) > 0 then
      present[#present + 1] = level
    end
  end
  return present, counts
end

--- Pick a level; its findings go to the quickfix list.
function M.filter()
  ensure_scanned(function()
    local all = state.findings()
    local levels, counts = levels_present(all)
    if #levels == 0 then
      return state.notify('nothing found.')
    end
    vim.ui.select(levels, {
      prompt = 'Show findings at level',
      format_item = function(level)
        return string.format('%-9s %d', core.LEVEL_LABEL[level], counts[level])
      end,
    }, function(level)
      if not level then
        return
      end
      local rows = {}
      for _, finding in ipairs(all) do
        if finding.level == level then
          rows[#rows + 1] = finding
        end
      end
      ui.to_quickfix(rows, scan.root(), 'Gandalf: ' .. core.LEVEL_LABEL[level])
      vim.cmd('copen')
    end)
  end)
end

--- Where the time went. Selecting a gate copies a ready-to-paste skip list,
--- since trimming the gate set is the only real lever on a slow scan.
function M.timings()
  local snapshot = state.snapshot()
  if not snapshot then
    return state.notify('no timings yet — run :GandalfScanAll first.')
  end
  local timed = {}
  for _, gate in ipairs(snapshot.payload.gates or {}) do
    if type(gate.duration) == 'number' then
      timed[#timed + 1] = gate
    end
  end
  if #timed == 0 then
    return state.notify('this run recorded no gate timings.')
  end
  table.sort(timed, function(a, b)
    return a.duration > b.duration
  end)
  vim.ui.select(timed, {
    prompt = 'Gate timings (slowest first) — pick one to copy a skip list',
    format_item = function(gate)
      return string.format('%-24s %6.1fs  %s', gate.name, gate.duration, gate.summary or '')
    end,
  }, function(gate)
    if not gate then
      return
    end
    local snippet = string.format('[gandalf]\nskip = ["%s"]\n', gate.name)
    vim.fn.setreg('+', snippet)
    vim.fn.setreg('"', snippet)
    state.notify(
      ('copied a skip list for %s. Paste it into a .gandalf.toml and point '):format(gate.name)
        .. 'config_path at that file to use it for editor scans only.'
    )
  end)
end

--- The scores in .gandalf-trend.jsonl, or an empty history when there is none.
local function read_trend(root)
  local log_path = vim.fs.joinpath(root, '.gandalf-trend.jsonl')
  if not vim.uv.fs_stat(log_path) then
    return {}
  end
  return core.parse_trend(table.concat(vim.fn.readfile(log_path), '\n'), vim.json.decode)
end

--- The scored commits oldest first, and the score each one moved from. Both are
--- for the sparkline and the deltas, which read forwards through history.
local function scored_series(commits, trend)
  local shorts, scores = {}, {}
  for i = #commits, 1, -1 do
    local entry = trend[commits[i].short]
    if entry then
      shorts[#shorts + 1] = commits[i].short
      scores[#scores + 1] = entry.score
    end
  end
  local previous = {}
  for i, short in ipairs(shorts) do
    if i > 1 then
      previous[short] = scores[i - 1]
    end
  end
  return scores, previous
end

local function history_prompt(scores, commits)
  if #scores > 0 then
    return string.format(
      'Score history — %s over %d of %d commit(s)',
      core.sparkline(scores),
      #scores,
      #commits
    )
  end
  return string.format('Score history — nothing scanned yet of %d commit(s)', #commits)
end

local function scan_commit(short)
  state.notify('scanning ' .. short .. '…')
  scan.run({
    kind = 'commit',
    commit = short,
    manual = true,
    reason = 'commit ' .. short,
    on_done = function(ok)
      if ok then
        M.report()
      end
    end,
  }, scan.cancel)
end

--- Score over time, from the log gandalf's own runs keep. `git log` supplies
--- the commits, including the ones nothing has scored yet, because "we have
--- never measured this" is part of the history too.
function M.history()
  local root = scan.root()
  local trend = read_trend(root)

  vim.system(
    { 'git', 'log', '-' .. HISTORY_COMMITS, '--format=%h%x1f%s%x1f%cs' },
    { text = true, cwd = root },
    function(out)
      vim.schedule(function()
        local commits = out.code == 0 and core.parse_log(out.stdout or '') or {}
        if #commits == 0 then
          return state.notify('no commits to show a history for.')
        end
        local scores, previous = scored_series(commits, trend)
        vim.ui.select(commits, {
          prompt = history_prompt(scores, commits),
          format_item = function(commit)
            local entry = trend[commit.short]
            local label = entry
                and string.format('%d/100 %-4s', entry.score, core.delta(entry.score, previous[commit.short]))
              or '— not scanned'
            return string.format('%-16s %s  %s', label, commit.short, commit.subject)
          end,
        }, function(commit)
          if commit then
            scan_commit(commit.short)
          end
        end)
      end)
    end
  )
end

function M.show_log()
  local lines = state.log_text()
  ui.float(#lines > 0 and lines or { 'nothing logged yet' }, {
    title = ' Gandalf log ',
    filetype = 'log',
  })
end

return M
