-- Which dependency a finding is about, and which one the cursor is on.

local fields = require('gandalf.core.fields')

local M = {}

-- What a tool calls the package a finding is about. gandalf leaves every gate's
-- own keys on the finding alongside the `_gandalf` block, so this reads them
-- directly rather than asking for a new normalized field.
--
-- Deliberately not a bare `name`: on a checkov or semgrep finding that is the
-- rule, and hovering a package only to be told about an unrelated rule is worse
-- than being told nothing.
M.PACKAGE_KEYS = { 'PkgName', 'pkg_name', 'PackageName', 'package_name', 'packageName' }
M.INSTALLED_KEYS = { 'InstalledVersion', 'installed_version', 'version', 'Version' }
M.FIXED_KEYS = { 'FixedVersion', 'fixed_version', 'fixed' }

--- The shapes a package name arrives in, most direct first. trivy says
--- `PkgName`, osv-scanner nests it under `affected[].package.name`, others use
--- a `package` object, and trivy's `PkgID` is `name@version`.
local EXTRACTORS = {
  function(raw)
    return fields.first_string(raw, M.PACKAGE_KEYS)
  end,
  function(raw)
    return type(raw.package) == 'string' and raw.package or ''
  end,
  function(raw)
    return type(raw.package) == 'table' and type(raw.package.name) == 'string' and raw.package.name or ''
  end,
  function(raw)
    local affected = raw.affected
    if type(affected) ~= 'table' or type(affected[1]) ~= 'table' then
      return ''
    end
    local nested = affected[1].package
    return type(nested) == 'table' and type(nested.name) == 'string' and nested.name or ''
  end,
  function(raw)
    return type(raw.PkgID) == 'string' and (raw.PkgID:match('^(.+)@[^@]*$') or '') or ''
  end,
}

--- The package a finding names, or ''.
function M.finding_package(raw)
  if type(raw) ~= 'table' then
    return ''
  end
  for _, extract in ipairs(EXTRACTORS) do
    local name = extract(raw)
    if name ~= '' then
      return name
    end
  end
  return ''
end

--- `fix_versions` is a list in pip-audit and a string everywhere else.
function M.fixed_version(raw)
  if type(raw) ~= 'table' then
    return ''
  end
  local list = raw.fix_versions
  if type(list) == 'table' and type(list[1]) == 'string' then
    return table.concat(list, ', ')
  end
  return fields.first_string(raw, M.FIXED_KEYS)
end

--- Lines that name no dependency at all: comments, section headers, pip flags.
local NOT_A_DEPENDENCY = { '^[#;]', '^//', '^%[%[?%a', '^%-' }

--- The shapes a manifest line takes, in the order they must be tried. A quoted
--- requirement is checked before a bare `key =`, or `dependencies = ["flask>=2"]`
--- would answer "dependencies".
local DEPENDENCY_PATTERNS = {
  "^gem%s+['\"]([^'\"]+)", -- Gemfile
  '^"([^"]+)"%s*:', -- package.json, and any JSON manifest
  "['\"]%s*([%a][%w%._%-]*)%s*[><=~!^]", -- "flask>=2" in a list
  '^([%w%._%-/]+)%s+v%d', -- go.mod
  '^([%a@][%w%._%-/]*)%s*[=~<>!]', -- serde = "1", flask==2.0
  '^([%a][%w%._%-]*)$', -- a bare requirements.txt line
}

--- The dependency named on a manifest line, or ''.
---
--- Pattern-based rather than per-format on purpose: the shapes above cover
--- requirements.txt, package.json, go.mod, Cargo.toml, pyproject.toml and
--- Gemfile between them, and a manifest nobody thought of still has a chance.
function M.package_at_cursor(line)
  local s = (line or ''):gsub('^%s+', ''):gsub('%s+$', '')
  if s == '' then
    return ''
  end
  for _, pattern in ipairs(NOT_A_DEPENDENCY) do
    if s:match(pattern) then
      return ''
    end
  end
  -- `flask[async]==2.0` is an ordinary requirements.txt line, and the extras
  -- sit exactly where the version operator is looked for. Only a bracket whose
  -- contents are extras-shaped is dropped, so Cargo's `features = ["full"]`
  -- (bracket not glued to a name, quotes inside) is left alone.
  s = s:gsub('([%a][%w%._%-]*)%[[%w%s,%._%-]*%]', '%1')
  for _, pattern in ipairs(DEPENDENCY_PATTERNS) do
    local name = s:match(pattern)
    if name then
      return name
    end
  end
  return ''
end

--- Findings that name `package`. Case-insensitive: tools disagree on the case
--- of a package name far more often than two real packages differ only by it.
function M.findings_for_package(findings, package)
  local want = package:lower()
  local out = {}
  for _, finding in ipairs(findings or {}) do
    if (finding.package or '') ~= '' and finding.package:lower() == want then
      out[#out + 1] = finding
    end
  end
  return out
end

return M
