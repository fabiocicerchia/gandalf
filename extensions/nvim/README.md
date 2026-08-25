# gandalf.nvim

Run Gandalf's quality gates from Neovim: inline diagnostics, the scorecard in a
float, and per-gate results as they land.

Gandalf runs ~30 pluggable gates over a repository — ruff, semgrep, bandit,
codeql, kics, trivy, licences, lizard, several LLM-judge gates — and produces a
Red/Amber/Green scorecard with a 0–100 score. This plugin drives that CLI.

```
gandalf AMBER 93/100          -- while idle
gandalf gates 12/37 · semgrep -- during a scan
```

It does not reimplement a single gate, and it does **not** reconcile finding
shapes. gandalf normalises its own findings ([`gandalf/findings.py`]) and
publishes the result on every finding, so this reads one shape instead of
carrying a copy of six key lists that would drift from the Python ones.

[`gandalf/findings.py`]: ../../src/gandalf/findings.py

## Requirements

- Neovim **0.11+**
- the `gandalf` CLI, or a checkout run as `python3 -m gandalf`
- `git` — gandalf resolves its scope from it
- `docker` for the gates that fall back to the scanner-tools image (optional)
- [plenary.nvim](https://github.com/nvim-lua/plenary.nvim) — for `make test` only

`:checkhealth gandalf` reports on all of it.

## Install

The plugin lives in `extensions/nvim/` of the gandalf repository.

**lazy.nvim**

```lua
{
  'fabiocicerchia/gandalf',
  rtp = 'extensions/nvim',
  cmd = { 'GandalfScan', 'GandalfScanAll', 'GandalfHover', 'GandalfReport', 'GandalfList' },
  opts = {},
}
```

**vim-plug**

```vim
Plug 'fabiocicerchia/gandalf', { 'rtp': 'extensions/nvim' }
```

```lua
require('gandalf').setup({})
```

Against a source checkout rather than an installed wrapper:

```lua
require('gandalf').setup({
  cmd = { 'python3', '-m', 'gandalf' },
  env = { PYTHONPATH = '/path/to/gandalf/src' },
})
```

## Configuration

```lua
require('gandalf').setup({
  enabled = true,
  cmd = { 'gandalf' },
  env = {},            -- merged over the inherited environment
  config_path = '',    -- a .gandalf.toml passed as --config
  exclude = {},        -- --exclude globs, repeated not joined
  extra_args = {},

  scan = {
    -- on_save | on_save_and_interval | interval | manual.
    -- There is no on_type: gates spawn real tools.
    trigger = 'on_save',
    debounce_ms = 1500,
    interval_minutes = 15,
    on_startup = true,
    timeout_ms = 600000,
    concurrency = 0,   -- 0 leaves gandalf's default (CPU count)
    use_cache = true,  -- --cache, workspace scans only
    llm = false,
    stream = true,     -- read per-gate results as they land
  },

  diagnostics = {
    enabled = true,
    min_level = 'info',
    severity = {
      critical = vim.diagnostic.severity.ERROR,
      high     = vim.diagnostic.severity.ERROR,
      medium   = vim.diagnostic.severity.WARN,
      low      = vim.diagnostic.severity.INFO,
      info     = vim.diagnostic.severity.INFO,
      unrated  = vim.diagnostic.severity.HINT,
    },
    max_per_file = 500,
  },
})
```

Every value is validated at `setup()`, so a wrong one is a message at startup
rather than a nil index inside a callback a minute into a scan.

## Commands

| Command | What it does |
| --- | --- |
| `:GandalfScanAll` | Scan the workspace |
| `:GandalfScan` | Scan the current file only |
| `:GandalfHover` | Explain the dependency under the cursor |
| `:GandalfReport` | The scorecard, in a float |
| `:GandalfReportLlm` | Rescan with the LLM summary, then open it |
| `:GandalfList` | Every finding, in the quickfix list |
| `:GandalfFilter` | Findings at one level, in the quickfix list |
| `:GandalfTimings` | Per-gate wall clock; picking one copies a skip list |
| `:GandalfHistory` | Score over time, from the trend log and `git log` |
| `:GandalfCancel` | Stop the running scan |
| `:GandalfLog` | What was run, and what came back |

## Why a scan is not on every keystroke

A gandalf run forks about thirty gates, several of them `docker run`. Every
trigger funnels through one policy: a burst of saves debounces into one run,
exactly one gandalf process exists at a time, and a manual run preempts an
automatic one. Every subprocess is `vim.system` with a callback and everything
touching the editor is inside `vim.schedule`, so nothing blocks.

With `--stream`, per-gate results are read as they arrive, so the quickfix list
fills during a run rather than at the end of it.

## Differences from the VS Code extension

Both drive the same CLI, so the findings are the same findings. The surface
differs.

**Dropped**

| Setting / command | Why |
| --- | --- |
| `useEditorExcludes` | Neovim has no `files.exclude` / `search.exclude` to merge |
| `path` + `pythonPath` | One `cmd` list replaces both — nothing has to guess whether a path is a wrapper or a checkout |
| `buildToolsImage` | It is one `docker build` in a gandalf checkout, better run where you can watch it. `:checkhealth` tells you when the image is missing |
| `exportReport` | gandalf writes the HTML itself; `--out-dir` says where |
| scope toggles, expand/collapse | Belong to the tree view |

**Different**

- **Findings pane** → the quickfix list, where a list of places to go belongs here.
- **Report** → a text float. gandalf's HTML report is a real document; open it from `--out-dir` in a browser rather than rendering a worse copy in a buffer.
- **Doctor** → `:checkhealth gandalf`.
- **Progress** → in the statusline, parsed from the progress line gandalf already draws on stderr.

## Development

```sh
make test    # 44 specs, headless, exactly as CI runs them
```

`tests/smoke.lua` drives the plugin against the real CLI and a real git
repository with nothing else on the runtimepath — that is what CI's smoke job
runs.

## License

Apache-2.0, with the rest of gandalf.
