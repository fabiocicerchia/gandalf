-- The command line for one scan.
--
-- Three groups, three questions: what to scan, what to write, and how to run it.
-- No `vim.` calls anywhere in core/, so all of it is testable under plain Lua.

local M = {}

local function append(argv, ...)
  for _, value in ipairs({ ... }) do
    argv[#argv + 1] = value
  end
end

--- What to scan. Nothing means the whole working tree, which is the default.
local function scope_args(opts)
  if opts.kind == 'file' and opts.rel_path then
    return { '--path', (opts.rel_path:gsub('\\', '/')) }
  end
  if opts.kind == 'commit' and opts.commit then
    return { '--commit', opts.commit }
  end
  return {}
end

--- What to write: the summary, the report, and where they go.
local function output_args(cfg, opts)
  local argv = {}
  if not (opts.llm or cfg.scan.llm) then
    append(argv, '--no-llm')
  end
  -- A one-file scorecard is not a report anyone wants, and the HTML is not
  -- rendered here in any case.
  append(argv, '--no-html')
  if opts.out_dir then
    append(argv, '--out-dir', opts.out_dir)
  end
  -- Editor scans stay out of the trend log: it is meant to be per commit, and a
  -- scan per save would swamp it. Scanning a named commit is the exception --
  -- that is exactly one entry for exactly one commit, which is what the log is.
  if opts.kind ~= 'commit' then
    append(argv, '--no-trend')
  end
  return argv
end

--- How to run it: the config, the concurrency, the cache and the stream.
local function run_args(cfg, opts)
  local argv = {}
  if cfg.config_path and cfg.config_path ~= '' then
    append(argv, '--config', cfg.config_path)
  end
  if cfg.scan.concurrency > 0 then
    append(argv, '--concurrency', tostring(cfg.scan.concurrency))
  end
  -- The cache is keyed per gate on a hash of the whole scanned file set, so a
  -- one-file scan would overwrite the workspace entries with a one-file hash
  -- and make the next full scan a complete miss.
  if cfg.scan.use_cache and opts.kind == 'workspace' then
    append(argv, '--cache')
  end
  if opts.stream then
    append(argv, '--stream')
  end
  return argv
end

--- Argv for one scan.
---@param cfg table resolved configuration
---@param opts table { kind = 'workspace'|'file'|'commit', rel_path?, commit? }
function M.scan_argv(cfg, opts)
  local argv = {}
  for _, group in ipairs({ scope_args(opts), output_args(cfg, opts), run_args(cfg, opts) }) do
    for _, arg in ipairs(group) do
      argv[#argv + 1] = arg
    end
  end
  -- Repeated rather than joined: a path may legitimately contain a comma.
  for _, pattern in ipairs(cfg.exclude) do
    append(argv, '--exclude', pattern)
  end
  -- Last, so what the user asked for wins.
  for _, extra in ipairs(cfg.extra_args) do
    append(argv, extra)
  end
  return argv
end

return M
