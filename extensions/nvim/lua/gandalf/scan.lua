-- Running gandalf once.
--
-- A gandalf run forks ~30 gates, several of them `docker run`. That is not
-- something to do on a keystroke, so every trigger funnels through here and
-- obeys the same rules the VS Code extension settled on: exactly one gandalf
-- process at a time, and a manual run preempts an automatic one.
--
-- Never blocks: vim.system with a callback, per-gate results read off stdout as
-- they arrive, and everything that touches the editor inside vim.schedule.

local core = require('gandalf.core')
local state = require('gandalf.state')
local ui = require('gandalf.ui')

local M = {}

local out_dir = nil

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

function M.root()
  return vim.fs.root(0, { '.git', '.hg' }) or vim.uv.cwd()
end

local function fail(message, opts)
  state.finish()
  state.log('scan failed: %s', message)
  state.notify(message, vim.log.levels.ERROR)
  if opts.on_done then
    opts.on_done(false)
  end
end

--- The environment gandalf is run with, over the inherited one.
local function scan_env(cfg)
  return vim.tbl_extend('force', {
    -- The progress line is TTY-gated; this turns it on for a piped child.
    GANDALF_PROGRESS = '1',
    -- The judge gates call the LLM whatever --no-llm says, and retry with
    -- backoff when it is unreachable. gandalf's default of 3 is right for CI
    -- and costs eleven seconds per scan in an editor; one still absorbs a blip.
    GANDALF_LLM_RETRIES = vim.env.GANDALF_LLM_RETRIES or '1',
  }, cfg.env)
end

--- Per-gate results as they land, so the list fills during the run.
local function on_stdout(events, plain, opts)
  return function(err, chunk)
    if err or not chunk then
      return
    end
    local found, text = events.feed(chunk)
    plain[#plain + 1] = text
    for _, event in ipairs(found) do
      if event.event == 'gate' then
        local findings = core.normalize_gate(event)
        vim.schedule(function()
          if state.push_stream(event.name, findings) and opts.on_gate then
            opts.on_gate(event)
          end
        end)
      end
    end
  end
end

local function on_stderr(parser, noise)
  return function(err, chunk)
    if err or not chunk then
      return
    end
    local progress, rest = parser.feed(chunk)
    noise[#noise + 1] = rest
    if progress then
      vim.schedule(function()
        state.set_progress(progress)
      end)
    end
  end
end

--- The report is the whole truth: read it, keep it, publish it.
local function accept(path, cfg, root, opts)
  local content = table.concat(vim.fn.readfile(path), '\n')
  local decoded_ok, payload = pcall(vim.json.decode, content)
  if not decoded_ok or type(payload) ~= 'table' then
    return fail('could not read the report gandalf wrote at ' .. path, opts)
  end

  local blocked, inapplicable = core.gates_by_status(payload)
  local findings = core.normalize(payload)
  state.set_snapshot({
    payload = payload,
    findings = findings,
    blocked = blocked,
    inapplicable = inapplicable,
    json_path = path,
    at = os.time(),
  })
  state.log('done: %s %d/100, %d finding(s)', payload.verdict, payload.score or 0, #findings)
  state.finish()
  ui.publish(state.findings(), cfg, root)
  if opts.on_done then
    opts.on_done(true)
  end
end

--- The process exited. Either it named a report, or the run is a failure.
local function on_exit(out, readers, cfg, root, opts)
  local text = table.concat(readers.plain) .. readers.events.flush()
  local diagnostics = table.concat(readers.noise) .. readers.progress.flush()
  local path = report_path(text)
  if path then
    return accept(path, cfg, root, opts)
  end
  -- Exit 1 is a red verdict, which is normal. No report at all is not.
  local detail = diagnostics ~= '' and diagnostics or (out.stderr or '')
  fail(
    ('gandalf produced no report (exit %s): %s'):format(
      tostring(out.code),
      vim.split(detail, '\n')[1] or 'no output'
    ),
    opts
  )
end

--- Whether this scan may start at all, given what is already running.
local function may_start(cfg, opts, cancel)
  if not cfg.enabled then
    return false
  end
  if not state.is_scanning() then
    return true
  end
  if not opts.manual then
    return false -- an automatic scan never queues behind another
  end
  state.log('preempting the running scan')
  cancel({ quiet = true })
  return true
end

--- Run one scan.
---@param opts table { kind, rel_path?, commit?, manual?, reason?, on_gate?, on_done? }
---@param cancel fun(opts:table) how to stop the run already in flight
function M.run(opts, cancel)
  opts = opts or {}
  local cfg = state.config()
  if not may_start(cfg, opts, cancel) then
    return
  end

  local root = M.root()
  local argv = core.scan_argv(
    cfg,
    vim.tbl_extend('force', opts, { out_dir = report_dir(), stream = cfg.scan.stream })
  )
  local cmd = vim.list_extend(vim.list_slice(cfg.cmd, 1, #cfg.cmd), argv)
  state.log('scan (%s): %s', opts.reason or 'command', table.concat(cmd, ' '))

  local readers = {
    events = core.event_parser(vim.json.decode),
    progress = core.progress_parser(),
    plain = {},
    noise = {},
  }
  state.begin_stream()

  local ok, started = pcall(vim.system, cmd, {
    text = true,
    cwd = root,
    env = scan_env(cfg),
    timeout = cfg.scan.timeout_ms,
    stdout = on_stdout(readers.events, readers.plain, opts),
    stderr = on_stderr(readers.progress, readers.noise),
  }, function(out)
    vim.schedule(function()
      on_exit(out, readers, cfg, root, opts)
    end)
  end)

  if not ok then
    state.log('could not run %s: %s', cmd[1], tostring(started))
    return fail(('could not run `%s` — see :checkhealth gandalf'):format(cmd[1]), opts)
  end
  state.begin(started)
end

function M.cancel(opts)
  opts = opts or {}
  local handle = state.handle()
  if not handle then
    if not opts.quiet then
      state.notify('no scan is running.')
    end
    return
  end
  pcall(function()
    handle:kill('sigterm')
  end)
  state.finish()
  if not opts.quiet then
    state.notify('scan cancelled.')
  end
end

return M
