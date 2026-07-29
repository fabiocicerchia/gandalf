# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.0.0 (2026-07-29)


### Features

* add .pre-commit-hooks.yaml so other repos can run gandalf as a hook ([b7f61f6](https://github.com/fabiocicerchia/gandalf/commit/b7f61f6b6cbab80aac5bbe6053a9c3856330c1d3))
* add install.sh one-liner installer ([4542a51](https://github.com/fabiocicerchia/gandalf/commit/4542a519e1d290ee1050caf8d4cf2f8c35b707e2))
* **badge:** add --badge shields.io endpoint badge output ([3860497](https://github.com/fabiocicerchia/gandalf/commit/3860497c917238af08622442f094282cc0b9f114))
* **cache:** add --cache to reuse gate results for unchanged files ([315bca5](https://github.com/fabiocicerchia/gandalf/commit/315bca5343915032f0a2e3a4330d471ecb3c15af))
* **gates:** add Rust language suite (cargo build/clippy/audit/test) ([60ed325](https://github.com/fabiocicerchia/gandalf/commit/60ed325ee52a2b3c3933411898e1c4e56679d87c))
* **junit:** add --junit XML report output ([95d1eec](https://github.com/fabiocicerchia/gandalf/commit/95d1eec1f2668bc38b96c87bbd49a8f04a6f5059))
* **report:** add RAG filter buttons and a raw diff view to the HTML report ([1adb447](https://github.com/fabiocicerchia/gandalf/commit/1adb44737bfa699ca87de3d03d83a24dffd0901e))
* **trend:** persist score history and show delta vs previous commit ([1587922](https://github.com/fabiocicerchia/gandalf/commit/158792270c28c07b74d0bfd22205d09028a731f6))


### Bug Fixes

* fix broken trivy-action pin, satisfy newer ruff rules across the gate suite ([#3](https://github.com/fabiocicerchia/gandalf/issues/3)) ([7d69b07](https://github.com/fabiocicerchia/gandalf/commit/7d69b075630ef28d5d540dbff7258da9245b6c36))
* **llm:** recognize "already addressed" as a stub phrase in gate summaries ([90ac4fe](https://github.com/fabiocicerchia/gandalf/commit/90ac4febf92c33b35161e24fab8ed2e9ce3b7898))

## [Unreleased]

## [0.1.0]

### Added

- Pluggable quality gates over a repo's working tree, staged changes, or a
  specific commit.
- Red/Amber/Green scorecard plus an LLM summary.

[Unreleased]: https://github.com/fabiocicerchia/gandalf/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/fabiocicerchia/gandalf/releases/tag/v0.1.0
