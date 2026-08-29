# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| latest  | ✅        |
| < latest| ❌        |

## Trust model

gandalf runs third-party scanners against a checkout and is normally invoked in
CI. Two inputs are privileged and must come from somewhere you already trust:

- **`GANDALF_GATES_PATH`** — directories gandalf imports Python from. Module-level
  code runs at import, and a gate loaded this way can replace a built-in one (a
  plugin named `gitleaks` becomes *the* `gitleaks` gate and can report a clean
  pass). Setting it is equivalent to arbitrary code execution as the user running
  gandalf; never derive it from a pull request or any contributor-editable input.
  See [docs/configuration.md](docs/configuration.md).
- **`.gandalf.toml`** — selects and disables gates, and sets the verdict policy.
  A pull request that edits it is asking to change what gates its own changes.
  Review changes to it as you would a change to your CI workflow.

Findings are reported, never executed: gandalf does not apply a scanner's
suggested fix on its own (`--fix` runs the tools' own fixers, explicitly).

## Reporting a Vulnerability

**Do not open a public issue for security problems.**

Report privately via [GitHub Security Advisories](https://github.com/fabiocicerchia/gandalf/security/advisories/new)
(preferred) or email **info@fabiocicerchia.it**.

Please include a description, reproduction steps, and impact. We aim to
acknowledge within 48 hours and to ship a fix or mitigation as soon as
practical, keeping you updated along the way.
