-- End-to-end: this plugin, the real gandalf CLI, a real git repository, nothing
-- else on the runtimepath.
--
-- The specs cover the ported logic in isolation; this covers the contract with
-- gandalf itself, which no amount of unit testing can.

local here = vim.fn.fnamemodify(vim.fn.resolve(debug.getinfo(1, 'S').source:sub(2)), ':p:h:h')
vim.opt.runtimepath:prepend(here)
vim.opt.swapfile = false
-- The runtimepath is added after startup, so plugin/ has already been walked.
vim.cmd('runtime! plugin/gandalf.lua')

local repo = vim.fn.fnamemodify(here, ':h:h')

-- Headless has no one to answer a prompt, and the default vim.ui.select blocks
-- on inputlist() waiting for a keypress. Stubbing it is what lets the commands
-- that offer a choice be exercised at all; each one picks the first item, which
-- is the branch worth covering.
local selected = {}
vim.ui.select = function(items, opts, on_choice)
  selected[#selected + 1] = (opts or {}).prompt or '?'
  on_choice(items[1], 1)
end
vim.ui.input = function(_, on_confirm)
  on_confirm(nil)
end

local failures = {}
local function check(ok, what)
  print((ok and '  ok   ' or '  FAIL ') .. what)
  if not ok then
    failures[#failures + 1] = what
  end
end

-- A tiny git repository, so the scan is seconds rather than minutes.
local project = vim.fn.tempname()
vim.fn.mkdir(project, 'p')
vim.fn.writefile({ 'import os', '', 'def f():', '    x = 1', '    return x' }, project .. '/app.py')
vim.fn.writefile({ '# fixture' }, project .. '/README.md')
-- An allowlist, so the smoke test is seconds rather than the several minutes a
-- full ~30-gate run takes. It also exercises `config_path`, which is how you
-- run a narrower gate set while you work.
vim.fn.writefile({ '[gandalf]', 'only = ["ruff", "mypy", "format"]' }, project .. '/.gandalf.toml')
for _, args in ipairs({
  { 'init', '-q' },
  { 'config', 'user.email', 'smoke@example.invalid' },
  { 'config', 'user.name', 'smoke' },
  { 'add', '-A' },
  { 'commit', '-qm', 'fixture' },
}) do
  vim.system(vim.list_extend({ 'git' }, args), { cwd = project }):wait()
end
vim.uv.chdir(project)

local cmd = vim.env.GANDALF_CMD and vim.split(vim.env.GANDALF_CMD, ' ') or { 'python3', '-m', 'gandalf' }

print('gandalf.nvim smoke test')
print('  cmd:     ' .. table.concat(cmd, ' '))
print('  project: ' .. project)

local gandalf = require('gandalf')
gandalf.setup({
  cmd = cmd,
  env = { PYTHONPATH = repo .. '/src' },
  config_path = project .. '/.gandalf.toml',
  scan = { trigger = 'manual', on_startup = false, timeout_ms = 300000 },
})

check(gandalf.is_setup(), 'setup() resolved a config')
check(gandalf.root() == vim.fs.normalize(project), 'found the project root')

vim.cmd.edit(project .. '/app.py')

local gates_seen = 0
local done = nil
gandalf.scan({
  kind = 'workspace',
  manual = true,
  reason = 'smoke',
  on_gate = function()
    gates_seen = gates_seen + 1
  end,
  on_done = function(ok)
    done = ok
  end,
})

check(gandalf.is_scanning(), 'the scan started')
vim.wait(300000, function()
  return done ~= nil
end, 500)
check(done == true, 'the scan completed')

local snapshot = gandalf.snapshot()
check(snapshot ~= nil, 'a report was read')

if snapshot then
  check(type(snapshot.payload.score) == 'number', 'it has a score (' .. tostring(snapshot.payload.score) .. '/100)')
  check(snapshot.payload.verdict ~= nil, 'it has a verdict (' .. tostring(snapshot.payload.verdict) .. ')')
  check(#(snapshot.payload.gates or {}) > 0, ('%d gate(s) ran'):format(#(snapshot.payload.gates or {})))
  check(gates_seen > 0, ('--stream reported %d gate(s) during the run'):format(gates_seen))
  check(gandalf.statusline():match('%d+/100') ~= nil, 'the statusline reads "' .. gandalf.statusline() .. '"')

  -- A gate whose tool is missing must be counted, not listed as a finding.
  for _, name in ipairs(snapshot.blocked) do
    for _, finding in ipairs(snapshot.findings) do
      check(finding.gate ~= name, ('%s is counted as blocked, not listed as a finding'):format(name))
    end
  end
  print(('  info blocked: %d, inapplicable: %d'):format(#snapshot.blocked, #snapshot.inapplicable))

  -- Every finding that names a file must name one that is really there: this is
  -- what proves gandalf's repo-relative `_gandalf.path` and our join agree.
  local placed, bad = 0, {}
  for _, finding in ipairs(snapshot.findings) do
    if finding.path ~= '' then
      if vim.uv.fs_stat(vim.fs.joinpath(project, finding.path)) then
        placed = placed + 1
      else
        bad[#bad + 1] = finding.path
      end
    end
  end
  check(#bad == 0, ('every placed finding resolves on disk (%d placed, %d bad)'):format(placed, #bad))

  -- And no rule id is a source snippet, which is the bug that started all this.
  local snippets = {}
  for _, finding in ipairs(snapshot.findings) do
    if finding.rule:find('\n') then
      snippets[#snippets + 1] = finding.gate
    end
  end
  check(#snippets == 0, 'no rule id is a multi-line source snippet')
end

for _, name in ipairs({
  'GandalfReport',
  'GandalfList',
  'GandalfFilter',
  'GandalfTimings',
  'GandalfLog',
  'GandalfCancel',
}) do
  local ok, err = pcall(vim.cmd, name)
  check(ok, name .. (ok and '' or ': ' .. tostring(err)))
  pcall(vim.cmd, 'cclose')
  pcall(vim.cmd, 'close')
end

check(#selected >= 2, ('the commands that offer a choice did (%d prompt(s))'):format(#selected))

print('')
if #failures > 0 then
  print(('%d check(s) failed:'):format(#failures))
  for _, what in ipairs(failures) do
    print('  - ' .. what)
  end
  vim.cmd('cq')
else
  print('all checks passed')
  vim.cmd('qa!')
end
