# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0](https://github.com/fabiocicerchia/gandalf/compare/v0.4.0...v0.5.0) (2026-08-18)


### Features

* add .pre-commit-hooks.yaml so other repos can run gandalf as a hook ([b7f61f6](https://github.com/fabiocicerchia/gandalf/commit/b7f61f6b6cbab80aac5bbe6053a9c3856330c1d3))
* add install.sh one-liner installer ([4542a51](https://github.com/fabiocicerchia/gandalf/commit/4542a519e1d290ee1050caf8d4cf2f8c35b707e2))
* **badge:** add --badge shields.io endpoint badge output ([3860497](https://github.com/fabiocicerchia/gandalf/commit/3860497c917238af08622442f094282cc0b9f114))
* **cache:** add --cache to reuse gate results for unchanged files ([315bca5](https://github.com/fabiocicerchia/gandalf/commit/315bca5343915032f0a2e3a4330d471ecb3c15af))
* **editors:** add a VS Code extension driving the gates from the IDE ([#32](https://github.com/fabiocicerchia/gandalf/issues/32)) ([40832d0](https://github.com/fabiocicerchia/gandalf/commit/40832d0788109a650a9f241553eb998f2af9edc8))
* **gates:** add Rust language suite (cargo build/clippy/audit/test) ([60ed325](https://github.com/fabiocicerchia/gandalf/commit/60ed325ee52a2b3c3933411898e1c4e56679d87c))
* **junit:** add --junit XML report output ([95d1eec](https://github.com/fabiocicerchia/gandalf/commit/95d1eec1f2668bc38b96c87bbd49a8f04a6f5059))
* PR-review GitHub Action with inline comments + code-scanning toggle ([#10](https://github.com/fabiocicerchia/gandalf/issues/10)) ([16e624f](https://github.com/fabiocicerchia/gandalf/commit/16e624f3b301a16fdbe15cc2aadf64c0f9373a44))
* **report:** add RAG filter buttons and a raw diff view to the HTML report ([1adb447](https://github.com/fabiocicerchia/gandalf/commit/1adb44737bfa699ca87de3d03d83a24dffd0901e))
* **trend:** persist score history and show delta vs previous commit ([1587922](https://github.com/fabiocicerchia/gandalf/commit/158792270c28c07b74d0bfd22205d09028a731f6))


### Bug Fixes

* **atheris:** stub the install probe so the log tests are not machine-dependent ([dfacfcf](https://github.com/fabiocicerchia/gandalf/commit/dfacfcf2a7cdccf3991e141e760aafdee874ac1e))
* bandit findings produced a 400-character SARIF rule id ([#35](https://github.com/fabiocicerchia/gandalf/issues/35)) ([a4560cf](https://github.com/fabiocicerchia/gandalf/commit/a4560cf91d4034746e9988f8347e804b23693f77))
* **ci:** install pytest even when the package has no [dev] extra ([618e383](https://github.com/fabiocicerchia/gandalf/commit/618e3838682f37da44ba7e18d3050e088c3a2f5b))
* fix broken trivy-action pin, satisfy newer ruff rules across the gate suite ([#3](https://github.com/fabiocicerchia/gandalf/issues/3)) ([7d69b07](https://github.com/fabiocicerchia/gandalf/commit/7d69b075630ef28d5d540dbff7258da9245b6c36))
* gandalf's SARIF upload failed every review it posted ([#33](https://github.com/fabiocicerchia/gandalf/issues/33)) ([c3cc105](https://github.com/fabiocicerchia/gandalf/commit/c3cc1059911506ccee72491d2aab1980da022569))
* **llm:** recognize "already addressed" as a stub phrase in gate summaries ([90ac4fe](https://github.com/fabiocicerchia/gandalf/commit/90ac4febf92c33b35161e24fab8ed2e9ce3b7898))
* **pr:** anchor inline comments to added lines and keep one sticky summary ([a882956](https://github.com/fabiocicerchia/gandalf/commit/a882956e9011aa05ba7ad33d3d1831d9d1c8f94b))
* **pre-commit:** stop check-yaml failing on Helm templates and multi-doc manifests ([7186c11](https://github.com/fabiocicerchia/gandalf/commit/7186c11a3501d804f637dbe407b0fe403ad220d8))
* restore the merge commit before uploading SARIF ([#27](https://github.com/fabiocicerchia/gandalf/issues/27)) ([afe5167](https://github.com/fabiocicerchia/gandalf/commit/afe51678ad51da42de086d854f601576b5e17874))
* security and code-quality findings ([#26](https://github.com/fabiocicerchia/gandalf/issues/26)) ([7b57a9d](https://github.com/fabiocicerchia/gandalf/commit/7b57a9d71c4e9cb42d6c5e07df4eee4136d7de29))
* **security:** skip the SARIF upload on private repos ([fb31a86](https://github.com/fabiocicerchia/gandalf/commit/fb31a8615a1171e218eaefa865ccb109354a4ca1))

## [0.4.0](https://github.com/fabiocicerchia/gandalf/compare/v0.3.0...v0.4.0) (2026-08-18)


### Features

* add .pre-commit-hooks.yaml so other repos can run gandalf as a hook ([b7f61f6](https://github.com/fabiocicerchia/gandalf/commit/b7f61f6b6cbab80aac5bbe6053a9c3856330c1d3))
* add install.sh one-liner installer ([4542a51](https://github.com/fabiocicerchia/gandalf/commit/4542a519e1d290ee1050caf8d4cf2f8c35b707e2))
* **badge:** add --badge shields.io endpoint badge output ([3860497](https://github.com/fabiocicerchia/gandalf/commit/3860497c917238af08622442f094282cc0b9f114))
* **cache:** add --cache to reuse gate results for unchanged files ([315bca5](https://github.com/fabiocicerchia/gandalf/commit/315bca5343915032f0a2e3a4330d471ecb3c15af))
* **editors:** add a VS Code extension driving the gates from the IDE ([#32](https://github.com/fabiocicerchia/gandalf/issues/32)) ([40832d0](https://github.com/fabiocicerchia/gandalf/commit/40832d0788109a650a9f241553eb998f2af9edc8))
* **gates:** add Rust language suite (cargo build/clippy/audit/test) ([60ed325](https://github.com/fabiocicerchia/gandalf/commit/60ed325ee52a2b3c3933411898e1c4e56679d87c))
* **junit:** add --junit XML report output ([95d1eec](https://github.com/fabiocicerchia/gandalf/commit/95d1eec1f2668bc38b96c87bbd49a8f04a6f5059))
* PR-review GitHub Action with inline comments + code-scanning toggle ([#10](https://github.com/fabiocicerchia/gandalf/issues/10)) ([16e624f](https://github.com/fabiocicerchia/gandalf/commit/16e624f3b301a16fdbe15cc2aadf64c0f9373a44))
* **report:** add RAG filter buttons and a raw diff view to the HTML report ([1adb447](https://github.com/fabiocicerchia/gandalf/commit/1adb44737bfa699ca87de3d03d83a24dffd0901e))
* **trend:** persist score history and show delta vs previous commit ([1587922](https://github.com/fabiocicerchia/gandalf/commit/158792270c28c07b74d0bfd22205d09028a731f6))


### Bug Fixes

* **atheris:** stub the install probe so the log tests are not machine-dependent ([dfacfcf](https://github.com/fabiocicerchia/gandalf/commit/dfacfcf2a7cdccf3991e141e760aafdee874ac1e))
* bandit findings produced a 400-character SARIF rule id ([#35](https://github.com/fabiocicerchia/gandalf/issues/35)) ([a4560cf](https://github.com/fabiocicerchia/gandalf/commit/a4560cf91d4034746e9988f8347e804b23693f77))
* **ci:** install pytest even when the package has no [dev] extra ([618e383](https://github.com/fabiocicerchia/gandalf/commit/618e3838682f37da44ba7e18d3050e088c3a2f5b))
* fix broken trivy-action pin, satisfy newer ruff rules across the gate suite ([#3](https://github.com/fabiocicerchia/gandalf/issues/3)) ([7d69b07](https://github.com/fabiocicerchia/gandalf/commit/7d69b075630ef28d5d540dbff7258da9245b6c36))
* gandalf's SARIF upload failed every review it posted ([#33](https://github.com/fabiocicerchia/gandalf/issues/33)) ([c3cc105](https://github.com/fabiocicerchia/gandalf/commit/c3cc1059911506ccee72491d2aab1980da022569))
* **llm:** recognize "already addressed" as a stub phrase in gate summaries ([90ac4fe](https://github.com/fabiocicerchia/gandalf/commit/90ac4febf92c33b35161e24fab8ed2e9ce3b7898))
* **pr:** anchor inline comments to added lines and keep one sticky summary ([a882956](https://github.com/fabiocicerchia/gandalf/commit/a882956e9011aa05ba7ad33d3d1831d9d1c8f94b))
* **pre-commit:** stop check-yaml failing on Helm templates and multi-doc manifests ([7186c11](https://github.com/fabiocicerchia/gandalf/commit/7186c11a3501d804f637dbe407b0fe403ad220d8))
* restore the merge commit before uploading SARIF ([#27](https://github.com/fabiocicerchia/gandalf/issues/27)) ([afe5167](https://github.com/fabiocicerchia/gandalf/commit/afe51678ad51da42de086d854f601576b5e17874))
* security and code-quality findings ([#26](https://github.com/fabiocicerchia/gandalf/issues/26)) ([7b57a9d](https://github.com/fabiocicerchia/gandalf/commit/7b57a9d71c4e9cb42d6c5e07df4eee4136d7de29))
* **security:** skip the SARIF upload on private repos ([fb31a86](https://github.com/fabiocicerchia/gandalf/commit/fb31a8615a1171e218eaefa865ccb109354a4ca1))

## [0.3.0](https://github.com/fabiocicerchia/gandalf/compare/v0.2.4...v0.3.0) (2026-08-18)


### Features

* **editors:** add a VS Code extension driving the gates from the IDE ([#32](https://github.com/fabiocicerchia/gandalf/issues/32)) ([40832d0](https://github.com/fabiocicerchia/gandalf/commit/40832d0788109a650a9f241553eb998f2af9edc8))

## [0.2.4](https://github.com/fabiocicerchia/gandalf/compare/v0.2.3...v0.2.4) (2026-08-16)


### Bug Fixes

* bandit findings produced a 400-character SARIF rule id ([#35](https://github.com/fabiocicerchia/gandalf/issues/35)) ([a4560cf](https://github.com/fabiocicerchia/gandalf/commit/a4560cf91d4034746e9988f8347e804b23693f77))

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
