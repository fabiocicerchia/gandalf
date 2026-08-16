# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.3](https://github.com/fabiocicerchia/gandalf/compare/v0.2.2...v0.2.3) (2026-08-16)


### Bug Fixes

* gandalf's SARIF upload failed every review it posted ([#33](https://github.com/fabiocicerchia/gandalf/issues/33)) ([c3cc105](https://github.com/fabiocicerchia/gandalf/commit/c3cc1059911506ccee72491d2aab1980da022569))

## [0.2.2](https://github.com/fabiocicerchia/gandalf/compare/v0.2.1...v0.2.2) (2026-08-13)


### Bug Fixes

* restore the merge commit before uploading SARIF ([#27](https://github.com/fabiocicerchia/gandalf/issues/27)) ([afe5167](https://github.com/fabiocicerchia/gandalf/commit/afe51678ad51da42de086d854f601576b5e17874))
* security and code-quality findings ([#26](https://github.com/fabiocicerchia/gandalf/issues/26)) ([7b57a9d](https://github.com/fabiocicerchia/gandalf/commit/7b57a9d71c4e9cb42d6c5e07df4eee4136d7de29))

## [0.2.1](https://github.com/fabiocicerchia/gandalf/compare/v0.2.0...v0.2.1) (2026-08-08)


### Bug Fixes

* **pr:** anchor inline comments to added lines and keep one sticky summary ([a882956](https://github.com/fabiocicerchia/gandalf/commit/a882956e9011aa05ba7ad33d3d1831d9d1c8f94b))

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
