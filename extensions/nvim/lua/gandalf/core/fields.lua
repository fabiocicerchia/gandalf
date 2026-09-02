-- Reading a value out of a finding whatever key its tool used for it.
--
-- Every gate passes its tool's output through untouched, so the same fact
-- arrives as `filename`, `file`, `path` or `file_path` depending on who
-- produced it. These two take the list of spellings and return the first one
-- that holds something.

local M = {}

function M.first_string(raw, keys)
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

function M.first_number(raw, keys)
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

return M
