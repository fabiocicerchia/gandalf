@domain:reporting @area:machine-formats @from:gandalf/outputs
Feature: Writing the run's report artifacts
  Gives CI pipelines, dashboards and editors a stable machine-readable record of every run, plus the HTML, SARIF, JUnit, badge and PR-comment files they ask for, in a place the operator controls.

  Background:
    Given a git repository with gandalf configured

  @id:reporting.machine-formats.008 @rule:reporting.artifacts.json-record-always-written @verified @source:src/gandalf/outputs.py#destination @test:tests/test_run.py#test_out_dir_and_no_trend_keep_the_worktree_clean @test:tests/test_run.py#test_reports_default_to_the_repo_and_record_a_trend
  Scenario Outline: Every run leaves a JSON record and an HTML report in the reports directory
    Given the operator passes <out_dir_option>
    When the operator runs gandalf
    Then a JSON report named gandalf-<scope>-<timestamp>.json is written to <directory>
    And an HTML report with the same name and an .html extension is written beside it
    And the directory is created if it was missing
    And the console names the JSON report path

    Examples:
      | out_dir_option             | directory                                           |
      | no --out-dir               | <repo>/reports                                      |
      | --out-dir artifacts/nested | artifacts/nested, and <repo>/reports is not created |

  @id:reporting.machine-formats.009 @rule:reporting.artifacts.optional-artifacts-on-request @inferred @source:src/gandalf/outputs.py#write_outputs
  Scenario Outline: Optional report formats are written only when asked for, beside the JSON record unless a path is given
    Given the operator passes <option>
    When the operator runs gandalf
    Then <artifact> is written to <default_path> when no path follows the option
    And it is written to the given path when one follows the option
    And the console names where it was written

    Examples:
      | option        | artifact                           | default_path                      |
      | --sarif       | a SARIF report                     | <reports>/<stem>.sarif            |
      | --junit       | a JUnit XML report                 | <reports>/<stem>.junit.xml        |
      | --badge       | a shields.io endpoint badge        | <reports>/<stem>-badge.json       |
      | --pr-comments | a pull-request review comment file | <reports>/<stem>-pr-comments.json |

  @id:reporting.machine-formats.010 @rule:reporting.artifacts.html-opt-out @inferred @source:src/gandalf/outputs.py#write_outputs
  Scenario: The HTML report can be switched off
    Given the operator passes --no-html
    When the operator runs gandalf
    Then no HTML report is written
    And the JSON report is still written

  @id:reporting.machine-formats.011 @rule:reporting.json-record.contract @verified @source:src/gandalf/outputs.py#build_payload @test:tests/test_run.py#test_payload_gates_carry_their_category @test:tests/test_run.py#test_json_leaves_only_the_payload_on_stdout
  Scenario: The JSON record carries the verdict, the policy decision and a reconciled view of every gate
    Given a run in which gates produced findings
    When the operator runs gandalf
    Then the record states the scope, commit, detected languages, score and the verdict as pass, warn or fail
    And it states whether the run passed under the policy, with the fail-on level, minimum score and reason
    And each gate entry states its category, whether it is blocking, whether it was unavailable and its duration
    And each finding keeps its tool's own fields and adds a _gandalf block with path, line, rule, message and severity
    And it lists skipped gates, disabled gates and the fixes applied

  @id:reporting.machine-formats.012 @rule:reporting.json-record.stdout-mode @verified @source:src/gandalf/outputs.py#write_outputs @test:tests/test_run.py#test_json_leaves_only_the_payload_on_stdout @test:tests/test_run.py#test_without_json_the_scorecard_stays_on_stdout
  Scenario Outline: With --json, standard output carries only the JSON record
    Given the operator passes <json_option>
    When the operator runs gandalf
    Then <stdout>
    And <report_line>

    Examples:
      | json_option | stdout                                                            | report_line                                        |
      | --json      | standard output parses as one JSON document whose verdict is pass | the "JSON report:" line appears on standard error  |
      | no --json   | standard output shows the human scorecard                         | the "JSON report:" line appears on standard output |

  @id:reporting.machine-formats.013 @rule:reporting.json-record.scanner-provenance @verified @source:src/gandalf/outputs.py#tool_report @test:tests/test_tool_provenance.py#test_report_names_the_image_only_when_one_was_used @test:tests/test_tool_provenance.py#test_versions_are_opt_in @test:tests/test_tool_provenance.py#test_no_tools_no_block
  Scenario Outline: The record says where each scanner came from, and its version only when asked
    Given <tools_used>
    And the operator passes <versions_option>
    When the operator runs gandalf
    Then the tools block <outcome>

    Examples:
      | tools_used                             | versions_option    | outcome                                                        |
      | ruff ran from the host PATH            | no --tool-versions | lists ruff with source host and no version, and names no image |
      | trivy ran from the gandalf-tools image | no --tool-versions | lists trivy with source image and names the image and its id   |
      | ruff ran from the host PATH            | --tool-versions    | lists ruff with source host and version "ruff 0.15.8"          |
      | no external scanner ran                | --tool-versions    | is empty                                                       |

  @id:reporting.machine-formats.014 @rule:reporting.pr-comments.post-to-pull-request @inferred @source:src/gandalf/outputs.py#write_outputs
  Scenario Outline: Asking to post to a pull request also writes the comment file and reports the posting result
    Given GITHUB_TOKEN is set in the environment
    And <repo_source>
    When the operator runs gandalf with --pr 42
    Then the pull-request review comment file is written with the number of inline comments shown
    And the comments are posted to pull request 42 of <repo>
    And the console shows "PR #42:" followed by the posting result

    Examples:
      | repo_source                                                 | repo         |
      | the operator passes --pr-repo acme/widgets                  | acme/widgets |
      | GITHUB_REPOSITORY is acme/widgets and no --pr-repo is given | acme/widgets |
