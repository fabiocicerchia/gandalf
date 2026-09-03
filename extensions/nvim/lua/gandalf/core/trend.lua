-- Score over time.
--
-- Every CLI run appends a line to .gandalf-trend.jsonl -- commit, score,
-- timestamp. Joined against `git log` it answers the question a single
-- scorecard cannot: is this getting better?

local M = {}

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

local TICKS =
  { '\226\150\129', '\226\150\130', '\226\150\131', '\226\150\132', '\226\150\133', '\226\150\134', '\226\150\135', '\226\150\136' }

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
