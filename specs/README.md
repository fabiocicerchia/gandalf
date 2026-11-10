# Specifications of gandalf

What this code does, one atomic Gherkin scenario per behaviour, read from the code by code-atlas.
Tags: `@verified` a test asserts it · `@inferred` read from the code only · `@gap` an entry point no test covers · `@human` written or amended by a person, never rewritten.

## Developer tooling

Building, installing, benchmarking, documenting and deploying gandalf itself.

- **Performance benchmarks**: [Charting benchmark results](developer-tooling/benchmarks/benchmark-chart.feature) (4)
- **Build and install**: [Installing and running gandalf from a checkout](developer-tooling/build-and-install/make-install-and-run.feature) (5)

## Editor integrations

Bringing gandalf into VS Code and Neovim through the CLI and its JSON report.

- **Automatic scanning**: [Automatic scanning](editor-integrations/auto-scan/editor-auto-scan.feature) (2), [Scanning automatically from Neovim](editor-integrations/auto-scan/nvim-automatic-scanning.feature) (3)
- **In-editor findings**: [Findings inside the editor](editor-integrations/editor-diagnostics/editor-findings.feature) (3), [Seeing findings in Neovim](editor-integrations/editor-diagnostics/nvim-in-editor-findings.feature) (8), [Reading the scorecard and dependency details in Neovim](editor-integrations/editor-diagnostics/nvim-scorecard-and-hover.feature) (6)
- **History and trends in the editor**: [Score history in the editor](editor-integrations/editor-history/editor-score-history.feature) (1), [Browsing score history in Neovim](editor-integrations/editor-history/nvim-score-history.feature) (3)
- **Scanning from the editor**: [Scanning from the editor](editor-integrations/editor-scans/editor-scan-commands.feature) (7), [Scanning a project from Neovim](editor-integrations/editor-scans/nvim-editor-scans.feature) (6)
- **Editor setup and health**: [Editor setup and health](editor-integrations/editor-setup/editor-setup-health.feature) (3), [Configuring and checking the Neovim plugin](editor-integrations/editor-setup/nvim-setup-and-health.feature) (4)
- **Run status and progress**: [Run status in the editor](editor-integrations/editor-status/editor-run-status.feature) (1), [Following a scan's progress and cost in Neovim](editor-integrations/editor-status/nvim-run-status.feature) (4)

## Findings and scoring

How individual problems are modelled, weighted, suppressed and fixed.

- **Autofix and suggestions**: [Applying tool fixes and reporting what they rewrote](findings/autofix/autofix-reporting.feature) (6), [Fixing findings in place and suggesting fixes](findings/autofix/gate-autofixes.feature) (5), [Suggesting one-click fixes on pull request comments](findings/autofix/one-click-fix-suggestions.feature) (7)
- **Findings and locations**: [Locating findings that tools only describe in text](findings/finding-model/finding-locations-from-prose.feature) (4), [Reading findings in one shape across every tool](findings/finding-model/normalised-findings-in-json-report.feature) (5)
- **Scoring and verdict**: [Scoring a run into one traffic light](findings/scoring/run-verdict-and-score.feature) (6), [Severity-weighted gate scoring](findings/scoring/severity-weighted-scoring.feature) (6)
- **Suppressions and baselines**: [Accepting known findings](findings/suppression/accepting-known-findings.feature) (4), [Recognising accepted findings in a baseline](findings/suppression/baseline-finding-identity.feature) (4)

## Gate extensibility

The public API third parties use to write their own gates and run external tools.

- **Plugin API**: [Adding custom gates](gate-extensibility/plugin-api/custom-gates.feature) (5)
- **External tool execution**: [Running scanner tools on the host or in the tools image](gate-extensibility/tool-execution/running-scanner-tools.feature) (6)
- **Not-checked outcomes**: [Reporting gates that could not check the code](gate-extensibility/unavailable-outcomes/not-checked-gate-outcomes.feature) (3)

## Quality gates

The built-in checks gandalf runs and how each turns tool output into a Red/Amber/Green outcome.

- **AI review gates**: [AI review gates driven by skill playbooks](quality-gates/ai-review/ai-review-gates.feature) (5), [Judging a change against an embedded review playbook](quality-gates/ai-review/skill-judged-gates.feature) (7), [Judging a change against a skill playbook](quality-gates/ai-review/skill-playbook-gates.feature) (1)
- **Build and CI checks**: [Live-target, CI workflow and compliance checks](quality-gates/build-and-ci/live-ci-and-compliance-gates.feature) (7)
- **Code health and style**: [Flagging complexity, documentation and style smells](quality-gates/code-health/code-health-gates.feature) (5)
- **Language toolchains**: [Checking each language's build, lint and tests](quality-gates/language-toolchains/language-toolchain-gates.feature) (8)
- **Security scanning**: [Catching leaked secrets and security flaws](quality-gates/security-scanning/security-scanning-gates.feature) (5)
- **Dependencies and licences**: [Judging dependencies, licences and repository posture](quality-gates/supply-chain/dependency-and-posture-gates.feature) (5)

## Reports and outputs

Every artifact and view a run produces for people, CI systems and pull requests.

- **AI summary**: [Writing the AI summary of a run](reporting/ai-summary/ai-summary.feature) (6)
- **Status badges**: [Publishing a status badge](reporting/badges/status-badge.feature) (1)
- **HTML report**: [Reading the HTML scorecard](reporting/html-report/html-report-reading.feature) (4), [Reading the HTML scorecard](reporting/html-report/html-report.feature) (7)
- **Live result streaming**: [Streaming gate results while a check runs](reporting/live-streaming/live-gate-results.feature) (4)
- **Machine-readable formats**: [Piping the JSON report from the command line](reporting/machine-formats/json-on-clean-stdout.feature) (1), [Publishing gate results as a JUnit test report](reporting/machine-formats/junit-report.feature) (5), [Writing the run's report artifacts](reporting/machine-formats/run-report-artifacts.feature) (6), [Publishing findings to code scanning as SARIF](reporting/machine-formats/sarif-code-scanning-report.feature) (7)
- **Pull request comments**: [Reviewing a pull request with gandalf findings](reporting/pull-request-comments/pr-review-content.feature) (6), [Publishing the review to a GitHub pull request](reporting/pull-request-comments/pr-review-publishing.feature) (4)
- **Score history**: [Tracking the score over time](reporting/score-trend/score-trend.feature) (6)
- **Terminal scorecard**: [Reading the run footer in the terminal](reporting/terminal-scorecard/terminal-run-footer.feature) (6), [Reading the scorecard in the terminal](reporting/terminal-scorecard/terminal-scorecard.feature) (8)

## Running a check

Deciding what gets evaluated and orchestrating the gates over it from the command line.

- **Command-line options**: [Validating command-line options](running-checks/command-line/command-line-option-validation.feature) (3), [Failing the build on the verdict](running-checks/command-line/exit-code-policy.feature) (1), [Watching a run's progress](running-checks/command-line/run-progress-line.feature) (2), [Running a check from the command line](running-checks/command-line/running-a-check.feature) (5)
- **Project configuration**: [Configuring a run from the repository](running-checks/configuration/project-configuration.feature) (3)
- **Debug logging**: [Tracing a run with debug logging](running-checks/debug-logging/debug-logging.feature) (5)
- **File selection and ignores**: [Excluding files from what every gate scans](running-checks/file-selection/excluding-files-from-gates.feature) (7)
- **Result caching**: [Reusing gate results between runs](running-checks/result-cache/reusing-gate-results.feature) (5)
- **Scan scope**: [Choosing what a run evaluates](running-checks/scan-scope/choosing-scan-scope.feature) (8)
- **Gate scheduling and concurrency**: [Bounding how hard and how long a run works](running-checks/scheduling/bounding-a-run.feature) (3), [Starting the heaviest gates first](running-checks/scheduling/gate-run-order.feature) (5)
