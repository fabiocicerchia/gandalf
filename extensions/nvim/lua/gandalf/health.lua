-- :checkhealth gandalf
--
-- Deliberately not a tool-by-tool inventory: gandalf already answers that per
-- gate on every scan, and keeping a copy of its tool list here is a thing that
-- would drift. What a scan cannot tell you is why it produced nothing at all,
-- so that is what this checks -- gandalf itself, git, docker, the scanner
-- image, and the endpoint the judge gates call.

local M = {}

local function run(cmd, args, timeout)
  local ok, out = pcall(function()
    local full = vim.list_extend(vim.list_slice(cmd, 1, #cmd), args)
    return vim.system(full, { text = true }):wait(timeout or 15000)
  end)
  if not ok then
    return nil, tostring(out)
  end
  return out, nil
end

function M.check()
  vim.health.start('gandalf')

  local gandalf = require('gandalf')
  local cfg = gandalf.config() or require('gandalf.config').resolve({})

  if vim.fn.has('nvim-0.11') ~= 1 then
    vim.health.error('Neovim 0.11 or newer is required (vim.system, vim.fs.relpath, vim.validate).')
  else
    vim.health.ok('Neovim ' .. tostring(vim.version()))
  end

  local shown = table.concat(cfg.cmd, ' ')
  if vim.fn.executable(cfg.cmd[1]) ~= 1 then
    vim.health.error(('`%s` is not executable'):format(cfg.cmd[1]), {
      'Install the wrapper with `make install`, or point cmd at a checkout:',
      "  require('gandalf').setup({ cmd = { 'python3', '-m', 'gandalf' },",
      "                             env = { PYTHONPATH = '/path/to/gandalf/src' } })",
    })
  else
    local out, err = run(cfg.cmd, { '--help' }, 20000)
    local help = out and ((out.stdout or '') .. (out.stderr or '')) or ''
    if not out then
      vim.health.error(('`%s` did not run: %s'):format(shown, err))
    elseif not help:match('gandalf') then
      vim.health.warn(('`%s` ran, but does not look like gandalf'):format(shown))
    else
      vim.health.ok(('`%s` runs'):format(shown))
      -- --stream is what fills the list during a multi-minute run rather than
      -- at the end of it.
      if help:match('%-%-stream') then
        vim.health.ok('this build supports --stream, so findings appear during a scan')
      else
        vim.health.warn('this build has no --stream support', {
          'Findings will only appear when the whole run finishes.',
        })
      end
    end
  end

  local root = gandalf.root()
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

  -- Most gates fall back to this image when their tool is not on PATH, so its
  -- absence is the single biggest reason a board is full of skipped gates.
  local image = cfg.env.GANDALF_TOOLS_IMAGE or vim.env.GANDALF_TOOLS_IMAGE or 'gandalf-tools'
  if vim.fn.executable('docker') ~= 1 then
    vim.health.warn('docker is not on PATH', {
      'Gates whose tool is not installed locally will report it unavailable.',
    })
  else
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

  local url = (cfg.env.GANDALF_LLM_URL or vim.env.GANDALF_LLM_URL or 'http://127.0.0.1:8787/v1'):gsub('/$', '')
  if vim.fn.executable('curl') == 1 then
    local out = run({ 'curl' }, { '-sS', '-o', '/dev/null', '-w', '%{http_code}', '-m', '3', url .. '/models' })
    if out and out.code == 0 and (out.stdout or ''):match('^2') then
      vim.health.ok('LLM endpoint (judge gates): ' .. url)
    else
      vim.health.info('LLM endpoint (judge gates) unreachable: ' .. url, {
        'The judge gates will skip. Everything else still runs.',
      })
    end
  end
end

return M
