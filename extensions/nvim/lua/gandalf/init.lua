-- setup(), the public API, and the scan policy.
--
-- A gandalf run forks ~30 gates, several of them `docker run`. That is not
-- something to do on a keystroke, so every trigger funnels through here and
-- obeys the same rules the VS Code extension settled on: debounce a burst of
-- saves into one run, exactly one gandalf process at a time, and a manual run
-- preempts an automatic one.

local config = require('gandalf.config')
local core = require('gandalf.core')
local ui = require('gandalf.ui')

local M = {}

local cfg = nil
--- The last completed run.
local snapshot = nil
--- Gates reported by the run in flight, keyed by name, so the list fills
--- during a scan instead of at the end of it.
local streaming = nil
local handle = nil
local progress = nil
local debounce_timer = nil
local sweep_timer = nil
local log_lines = {}
local out_dir = nil

local function log(fmt, ...)
  log_lines[#log_lines + 1] = string.format('[%s] ' .. fmt, os.date('%H:%M:%S'), ...)
  if #log_lines > 500 then
    table.remove(log_lines, 1)
  end
end

local function notify(msg, level)
  vim.notify('Gandalf: ' .. msg, level or vim.log.levels.INFO)
end

function M.is_setup()
  return cfg ~= nil
end

function M.config()
  return cfg
end

function M.log_text()
  return log_lines
end

function M.root()
  return vim.fs.root(0, { '.git', '.hg' }) or vim.uv.cwd()
end

function M.snapshot()
  return snapshot
end

function M.is_scanning()
  return handle ~= nil
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
    if progress then
      return 'gandalf ' .. core.describe_progress(progress)
    end
    return 'gandalf scanning'
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

-- --- running gandalf ---------------------------------------------------------

local function report_dir()
  if not out_dir then
    out_dir = vim.fs.joinpath(vim.fn.stdpath('state'), 'gandalf', 'reports')
    vim.fn.mkdir(out_dir, 'p')
  end
  return out_dir
end

--- Where gandalf named its JSON report, from the line it prints.
local function report_path(text)
  return text:match('JSON report:%s*([^\n]+)')
end

local function finish(ok, message)
  handle = nil
  streaming = nil
  progress = nil
  if not ok and message then
    log('scan failed: %s', message)
    notify(message, vim.log.levels.ERROR)
  end
end

--- Run one scan. Never blocks: vim.system with a callback, per-gate results
--- read off stdout as they arrive, and everything that touches the editor
--- inside vim.schedule.
function M.scan(opts)
  opts = opts or {}
  if not cfg.enabled then
    return
  end
  if handle then
    if not opts.manual then
      return -- an automatic scan never queues behind another
    end
    log('preempting the running scan')
    M.cancel({ quiet = true })
  end

  local root = M.root()
  local argv = core.scan_argv(
    cfg,
    vim.tbl_extend('force', opts, { out_dir = report_dir(), stream = cfg.scan.stream })
  )
  local cmd = vim.list_extend(vim.list_slice(cfg.cmd, 1, #cfg.cmd), argv)
  log('scan (%s): %s', opts.reason or 'command', table.concat(cmd, ' '))

  local events = core.event_parser(vim.json.decode)
  local progress_parser = core.progress_parser()
  local plain, noise = {}, {}
  streaming = {}

  local env = vim.tbl_extend('force', {
    -- The progress line is TTY-gated; this turns it on for a piped child.
    GANDALF_PROGRESS = '1',
    -- The judge gates call the LLM whatever --no-llm says, and retry with
    -- backoff when it is unreachable. gandalf's default of 3 is right for CI
    -- and costs eleven seconds per scan in an editor; one still absorbs a blip.
    GANDALF_LLM_RETRIES = vim.env.GANDALF_LLM_RETRIES or '1',
  }, cfg.env)

  local ok, started = pcall(vim.system, cmd, {
    text = true,
    cwd = root,
    env = env,
    timeout = cfg.scan.timeout_ms,
    stdout = function(err, chunk)
      if err or not chunk then
        return
      end
      local found, text = events.feed(chunk)
      plain[#plain + 1] = text
      for _, event in ipairs(found) do
        if event.event == 'gate' then
          local findings = core.normalize_gate(event)
          vim.schedule(function()
            if streaming then
              streaming[event.name] = findings
              if opts.on_gate then
                opts.on_gate(event)
              end
            end
          end)
        end
      end
    end,
    stderr = function(err, chunk)
      if err or not chunk then
        return
      end
      local state, rest = progress_parser.feed(chunk)
      noise[#noise + 1] = rest
      if state then
        vim.schedule(function()
          progress = state
        end)
      end
    end,
  }, function(out)
    vim.schedule(function()
      local text = table.concat(plain) .. events.flush()
      local diagnostics = table.concat(noise) .. progress_parser.flush()
      local path = report_path(text)

      if not path then
        -- Exit 1 is a red verdict, which is normal. No report at all is not.
        finish(false, ('gandalf produced no report (exit %s): %s'):format(
          tostring(out.code),
          vim.split(diagnostics ~= '' and diagnostics or (out.stderr or ''), '\n')[1] or 'no output'
        ))
        if opts.on_done then
          opts.on_done(false)
        end
        return
      end

      local content = table.concat(vim.fn.readfile(path), '\n')
      local decoded_ok, payload = pcall(vim.json.decode, content)
      if not decoded_ok or type(payload) ~= 'table' then
        finish(false, 'could not read the report gandalf wrote at ' .. path)
        if opts.on_done then
          opts.on_done(false)
        end
        return
      end

      local blocked, inapplicable = core.gates_by_status(payload)
      snapshot = {
        payload = payload,
        findings = core.normalize(payload),
        blocked = blocked,
        inapplicable = inapplicable,
        json_path = path,
        at = os.time(),
      }
      log(
        'done: %s %d/100, %d finding(s)',
        payload.verdict,
        payload.score or 0,
        #snapshot.findings
      )
      finish(true)
      ui.publish(M.findings(), cfg, root)
      if opts.on_done then
        opts.on_done(true)
      end
    end)
  end)

  if not ok then
    log('could not run %s: %s', cmd[1], tostring(started))
    finish(false, ('could not run `%s` — see :checkhealth gandalf'):format(cmd[1]))
    if opts.on_done then
      opts.on_done(false)
    end
    return
  end
  handle = started
end

function M.cancel(opts)
  opts = opts or {}
  if not handle then
    if not opts.quiet then
      notify('no scan is running.')
    end
    return
  end
  pcall(function()
    handle:kill('sigterm')
  end)
  finish(true)
  if not opts.quiet then
    notify('scan cancelled.')
  end
end

-- --- triggers ----------------------------------------------------------------

local function schedule_scan(opts)
  if debounce_timer then
    debounce_timer:stop()
    debounce_timer:close()
  end
  debounce_timer = vim.uv.new_timer()
  debounce_timer:start(cfg.scan.debounce_ms, 0, function()
    debounce_timer:stop()
    debounce_timer:close()
    debounce_timer = nil
    vim.schedule(function()
      M.scan(opts)
    end)
  end)
end

local function arm_sweep()
  if sweep_timer then
    sweep_timer:stop()
    sweep_timer:close()
    sweep_timer = nil
  end
  local trigger = cfg.scan.trigger
  if trigger ~= 'interval' and trigger ~= 'on_save_and_interval' then
    return
  end
  local period = cfg.scan.interval_minutes * 60000
  sweep_timer = vim.uv.new_timer()
  sweep_timer:start(period, period, function()
    vim.schedule(function()
      M.scan({ kind = 'workspace', reason = 'periodic sweep' })
    end)
  end)
end

local function attach_autocmds()
  local group = vim.api.nvim_create_augroup('gandalf', { clear = true })

  vim.api.nvim_create_autocmd('BufWritePost', {
    group = group,
    callback = function(event)
      local trigger = cfg.scan.trigger
      if not cfg.enabled or (trigger ~= 'on_save' and trigger ~= 'on_save_and_interval') then
        return
      end
      local root = M.root()
      local rel = vim.fs.relpath(root, vim.fs.normalize(event.match))
      -- Never let gandalf's own output re-trigger gandalf.
      if not rel or rel:match('^%.git/') or rel:match('^reports/') or vim.fs.basename(rel):match('^%.gandalf%-') then
        return
      end
      schedule_scan({ kind = 'file', rel_path = rel, reason = 'saved ' .. rel })
    end,
  })

  -- A file opened after the scan still gets its squiggles.
  vim.api.nvim_create_autocmd('BufReadPost', {
    group = group,
    callback = function()
      if snapshot then
        vim.schedule(function()
          ui.publish(M.findings(), cfg, M.root())
        end)
      end
    end,
  })
end

-- --- commands ----------------------------------------------------------------

local function ensure_scanned(cb)
  if snapshot then
    return cb()
  end
  notify('scanning…')
  M.scan({ kind = 'workspace', manual = true, reason = 'report', on_done = function(ok)
    if ok then
      cb()
    end
  end })
end

function M.report()
  ensure_scanned(function()
    ui.float(ui.report_lines(snapshot), { title = ' Gandalf scorecard ', filetype = 'gandalf-report' })
  end)
end

--- Explain the dependency under the cursor: what gandalf found against it, and
--- what it could not check.
function M.hover()
  local package = core.package_at_cursor(vim.api.nvim_get_current_line())
  if package == '' then
    return notify('no dependency on this line.')
  end
  ensure_scanned(function()
    local matched = core.findings_for_package(M.findings(), package)
    ui.float(ui.hover_lines(package, matched, snapshot), {
      title = ' ' .. package .. ' ',
      filetype = 'gandalf-hover',
    })
  end)
end

--- Every finding, in the quickfix list.
function M.list()
  ensure_scanned(function()
    local findings = M.findings()
    if #findings == 0 then
      return notify('nothing found.')
    end
    ui.to_quickfix(findings, M.root(), 'Gandalf')
    vim.cmd('copen')
  end)
end

--- Pick a level; its findings go to the quickfix list.
function M.filter()
  ensure_scanned(function()
    local all = M.findings()
    local counts = {}
    for _, finding in ipairs(all) do
      counts[finding.level] = (counts[finding.level] or 0) + 1
    end
    local items = {}
    for _, level in ipairs(core.LEVELS) do
      if (counts[level] or 0) > 0 then
        items[#items + 1] = level
      end
    end
    if #items == 0 then
      return notify('nothing found.')
    end
    vim.ui.select(items, {
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
      ui.to_quickfix(rows, M.root(), 'Gandalf: ' .. core.LEVEL_LABEL[level])
      vim.cmd('copen')
    end)
  end)
end

--- Where the time went. Selecting gates copies a ready-to-paste skip list,
--- since trimming the gate set is the only real lever on a slow scan.
function M.timings()
  if not snapshot then
    return notify('no timings yet — run :GandalfScanAll first.')
  end
  local timed = {}
  for _, gate in ipairs(snapshot.payload.gates or {}) do
    if type(gate.duration) == 'number' then
      timed[#timed + 1] = gate
    end
  end
  if #timed == 0 then
    return notify('this run recorded no gate timings.')
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
    notify(('copied a skip list for %s. Paste it into a .gandalf.toml and point '):format(gate.name)
      .. 'config_path at that file to use it for editor scans only.')
  end)
end

--- Score over time, from the log gandalf's own runs keep.
function M.history()
  local root = M.root()
  local trend = {}
  local log_path = vim.fs.joinpath(root, '.gandalf-trend.jsonl')
  if vim.uv.fs_stat(log_path) then
    trend = core.parse_trend(table.concat(vim.fn.readfile(log_path), '\n'), vim.json.decode)
  end

  vim.system(
    { 'git', 'log', '-40', '--format=%h%x1f%s%x1f%cs' },
    { text = true, cwd = root },
    function(out)
      vim.schedule(function()
        local commits = out.code == 0 and core.parse_log(out.stdout or '') or {}
        if #commits == 0 then
          return notify('no commits to show a history for.')
        end
        local scored, scores = {}, {}
        for i = #commits, 1, -1 do
          local entry = trend[commits[i].short]
          if entry then
            scored[#scored + 1] = commits[i].short
            scores[#scores + 1] = entry.score
          end
        end
        local line = core.sparkline(scores)
        local previous = {}
        for i, short in ipairs(scored) do
          if i > 1 then
            previous[short] = scores[i - 1]
          end
        end

        vim.ui.select(commits, {
          prompt = #scored > 0
              and string.format('Score history — %s over %d of %d commit(s)', line, #scored, #commits)
            or string.format('Score history — nothing scanned yet of %d commit(s)', #commits),
          format_item = function(commit)
            local entry = trend[commit.short]
            local label = entry
                and string.format('%d/100 %-4s', entry.score, core.delta(entry.score, previous[commit.short]))
              or '— not scanned'
            return string.format('%-16s %s  %s', label, commit.short, commit.subject)
          end,
        }, function(commit)
          if commit then
            notify('scanning ' .. commit.short .. '…')
            M.scan({
              kind = 'commit',
              commit = commit.short,
              manual = true,
              reason = 'commit ' .. commit.short,
              on_done = function(ok)
                if ok then
                  M.report()
                end
              end,
            })
          end
        end)
      end)
    end
  )
end

function M.show_log()
  ui.float(#log_lines > 0 and log_lines or { 'nothing logged yet' }, { title = ' Gandalf log ', filetype = 'log' })
end

-- --- setup -------------------------------------------------------------------

function M.setup(opts)
  cfg = config.resolve(opts)
  if not cfg.enabled then
    ui.clear()
    return
  end
  attach_autocmds()
  arm_sweep()
  if cfg.scan.on_startup and cfg.scan.trigger ~= 'manual' then
    -- Let the session settle before forking ~30 gates.
    vim.defer_fn(function()
      M.scan({ kind = 'workspace', reason = 'startup' })
    end, 5000)
  end
end

return M
