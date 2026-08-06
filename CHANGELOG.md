# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/fabiocicerchia/gandalf/compare/v0.1.0...v0.2.0) (2026-08-06)


### Features

* PR-review GitHub Action with inline comments + code-scanning toggle ([#10](https://github.com/fabiocicerchia/gandalf/issues/10)) ([16e624f](https://github.com/fabiocicerchia/gandalf/commit/16e624f3b301a16fdbe15cc2aadf64c0f9373a44))


### Bug Fixes

* **atheris:** stub the install probe so the log tests are not machine-dependent ([dfacfcf](https://github.com/fabiocicerchia/gandalf/commit/dfacfcf2a7cdccf3991e141e760aafdee874ac1e))
* **ci:** install pytest even when the package has no [dev] extra ([618e383](https://github.com/fabiocicerchia/gandalf/commit/618e3838682f37da44ba7e18d3050e088c3a2f5b))
* **pre-commit:** stop check-yaml failing on Helm templates and multi-doc manifests ([7186c11](https://github.com/fabiocicerchia/gandalf/commit/7186c11a3501d804f637dbe407b0fe403ad220d8))
* **security:** skip the SARIF upload on private repos ([fb31a86](https://github.com/fabiocicerchia/gandalf/commit/fb31a8615a1171e218eaefa865ccb109354a4ca1))

## [Unreleased]

## [0.1.0]

### Added

- Pluggable quality gates over a repo's working tree, staged changes, or a
  specific commit.
- Red/Amber/Green scorecard plus an LLM summary.

[Unreleased]: https://github.com/fabiocicerchia/gandalf/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/fabiocicerchia/gandalf/releases/tag/v0.1.0
