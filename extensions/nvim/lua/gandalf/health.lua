-- :checkhealth gandalf
--
-- Deliberately not a tool-by-tool inventory: gandalf already answers that per
-- gate on every scan, and keeping a copy of its tool list here is a thing that
-- would drift. What a scan cannot tell you is why it produced nothing at all,
-- so that is what this checks -- gandalf itself, git, docker, the scanner
-- image, and the endpoint the judge gates call. One function per section, in
-- the order they are reported.

local M = {}

local HELP_TIMEOUT_MS = 20000
local RUN_TIMEOUT_MS = 15000
local DEFAULT_TOOLS_IMAGE = 'gandalf-tools'
local DEFAULT_LLM_URL = 'http://127.0.0.1:8787/v1'

local function run(cmd, args, timeout)
  local ok, out = pcall(function()
    local full = vim.list_extend(vim.list_slice(cmd, 1, #cmd), args)
    return vim.system(full, { text = true }):wait(timeout or RUN_TIMEOUT_MS)
  end)
  if not ok then
    return nil, tostring(out)
  end
  return out, nil
end

local function check_neovim()
  if vim.fn.has('nvim-0.11') ~= 1 then
    vim.health.error('Neovim 0.11 or newer is required (vim.system, vim.fs.relpath, vim.validate).')
  else
    vim.health.ok('Neovim ' .. tostring(vim.version()))
  end
end

--- Whether findings will appear during a run or only at the end of it.
local function check_stream_support(help)
  -- --stream is what fills the list during a multi-minute run rather than at
  -- the end of it.
  if help:match('%-%-stream') then
    vim.health.ok('this build supports --stream, so findings appear during a scan')
  else
    vim.health.warn('this build has no --stream support', {
      'Findings will only appear when the whole run finishes.',
    })
  end
end

--- Does `cmd` exist, does it run, and is it gandalf?
local function check_command(cfg)
  local shown = table.concat(cfg.cmd, ' ')
  if vim.fn.executable(cfg.cmd[1]) ~= 1 then
    vim.health.error(('`%s` is not executable'):format(cfg.cmd[1]), {
      'Install the wrapper with `make install`, or point cmd at a checkout:',
      "  require('gandalf').setup({ cmd = { 'python3', '-m', 'gandalf' },",
      "                             env = { PYTHONPATH = '/path/to/gandalf/src' } })",
    })
    return
  end

  local out, err = run(cfg.cmd, { '--help' }, HELP_TIMEOUT_MS)
  if not out then
    vim.health.error(('`%s` did not run: %s'):format(shown, err))
    return
  end
  local help = (out.stdout or '') .. (out.stderr or '')
  if not help:match('gandalf') then
    vim.health.warn(('`%s` ran, but does not look like gandalf'):format(shown))
    return
  end
  vim.health.ok(('`%s` runs'):format(shown))
  check_stream_support(help)
end

--- gandalf resolves its scope from git; without a repository there is nothing
--- to scan, and without git there is no way to ask.
local function check_repository(root)
  vim.health.info('project root: ' .. tostring(root))
  if vim.uv.fs_stat(vim.fs.joinpath(root, '.git')) == nil then
    vim.health.warn(root .. ' is not a git repository', {
      'gandalf resolves its scope from git; without one there is nothing to scan.',
    })
  else
    vim.health.ok('git repository')
  end
  if vim.fn.executable('git') ~= 1 then
    vim.health.error('git is not on PATH — gandalf has no scope to resolve')
  end
end

--- Most gates fall back to the tools image when their tool is not on PATH, so
--- its absence is the single biggest reason a board is full of skipped gates.
local function check_tools_image(cfg)
  local image = cfg.env.GANDALF_TOOLS_IMAGE or vim.env.GANDALF_TOOLS_IMAGE or DEFAULT_TOOLS_IMAGE
  if vim.fn.executable('docker') ~= 1 then
    vim.health.warn('docker is not on PATH', {
      'Gates whose tool is not installed locally will report it unavailable.',
    })
    return
  end
  local out = run({ 'docker' }, { 'image', 'inspect', image })
  if out and out.code == 0 then
    vim.health.ok(('scanner tools: "%s" present'):format(image))
  else
    vim.health.warn(('scanner tools: "%s" missing'):format(image), {
      'Most gates will report their tool unavailable.',
      'Build it from a gandalf checkout: make tools',
    })
  end
end

--- The judge gates call this whatever --no-llm says; everything else runs
--- without it, so an unreachable endpoint is information, not a failure.
local function check_llm(cfg)
  local url = (cfg.env.GANDALF_LLM_URL or vim.env.GANDALF_LLM_URL or DEFAULT_LLM_URL):gsub('/$', '')
  if vim.fn.executable('curl') ~= 1 then
    return
  end
  local out = run({ 'curl' }, { '-sS', '-o', '/dev/null', '-w', '%{http_code}', '-m', '3', url .. '/models' })
  if out and out.code == 0 and (out.stdout or ''):match('^2') then
    vim.health.ok('LLM endpoint (judge gates): ' .. url)
  else
    vim.health.info('LLM endpoint (judge gates) unreachable: ' .. url, {
      'The judge gates will skip. Everything else still runs.',
    })
  end
end

function M.check()
  vim.health.start('gandalf')

  local gandalf = require('gandalf')
  local cfg = gandalf.config() or require('gandalf.config').resolve({})

  check_neovim()
  check_command(cfg)
  check_repository(gandalf.root())
  check_tools_image(cfg)
  check_llm(cfg)
end

return M
