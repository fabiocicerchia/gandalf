-- gandalf's `--stream` output, and the progress line it draws on stderr.
--
-- One NDJSON line per gate as it finishes. Without reading them nothing reaches
-- the user until the final report is written, so a pane sits empty for the whole
-- run. The aggregate still comes only from the report -- a verdict and a
-- composite score are properties of the whole run, and no single gate result can
-- produce them.
--
-- Event lines share stdout with the human scorecard, which is printed at the
-- end, so they are picked out by their prefix and everything else is handed back
-- untouched.

local M = {}

local EVENT_PREFIX = '{"event"'

local function is_outcome(value)
  return value == 'pass' or value == 'warn' or value == 'fail'
end

local function num(value, fallback)
  return type(value) == 'number' and value or fallback
end

local function str(value, fallback)
  return type(value) == 'string' and value or fallback
end

--- The "here is what I am about to run" line a stream opens with.
local function start_event(parsed)
  if type(parsed.gates) ~= 'number' then
    return nil
  end
  return { event = 'start', scope = tostring(parsed.scope or ''), gates = parsed.gates }
end

--- One finished gate. A name and an outcome are what make it one.
local function gate_event(parsed)
  if type(parsed.name) ~= 'string' or not is_outcome(parsed.outcome) then
    return nil
  end
  return {
    event = 'gate',
    index = num(parsed.index, 0),
    total = num(parsed.total, 0),
    name = parsed.name,
    outcome = parsed.outcome,
    score = num(parsed.score, 0),
    summary = str(parsed.summary, ''),
    findings = type(parsed.findings) == 'table' and parsed.findings or {},
    category = str(parsed.category, nil),
    duration = num(parsed.duration, nil),
  }
end

--- Validate rather than trust: a malformed line must not poison the pane.
local function to_event(parsed)
  if type(parsed) ~= 'table' then
    return nil
  end
  if parsed.event == 'start' then
    return start_event(parsed)
  end
  if parsed.event == 'gate' then
    return gate_event(parsed)
  end
  return nil
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

return M
