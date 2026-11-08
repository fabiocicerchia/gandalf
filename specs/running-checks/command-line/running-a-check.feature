@domain:running-checks @area:command-line @from:gandalf/gandalf
Feature: Running a check from the command line
  Lets an operator or CI job run gandalf over a repository and act on a pass/fail exit status without reading the code.

  Background:
    Given a git repository with gandalf configuration

  @id:running-checks.command-line.004 @rule:cli.run.exit-status-follows-verdict @verified @source:src/gandalf/__main__.py#main @test:tests/test_run.py#test_exclude_narrows_the_scan_end_to_end @test:tests/test_run.py#test_stream_applies_baseline_suppression
  Scenario Outline: The run exits non-zero when the verdict fails the policy
    Given the default verdict policy
    And a repository whose files <state>
    When the operator runs gandalf
    Then the scorecard is printed
    And the process exits with status <status>

    Examples:
      | state                                       | status |
      | all compile cleanly                         | 0      |
      | include a Python file that does not compile | 1      |

  @id:running-checks.command-line.005 @rule:cli.run.refuses-when-nothing-to-run @inferred @source:src/gandalf/__main__.py#_select_gates
  Scenario Outline: A run with no gates left to run is refused with status 2
    Given <situation>
    When the operator runs gandalf <flags>
    Then the error "<message>" is printed
    And no gate runs and no report is written
    And the process exits with status 2

    Examples:
      | situation                                                      | flags         | message                                                    |
      | the project configuration switches off every gate              |               | all gates disabled by config selection                     |
      | the configuration keeps only LLM-backed gates such as grill_me | with --no-llm | every remaining gate is LLM-backed, and --no-llm was given |
      | no gates are installed                                         |               | no gates discovered                                        |

  @id:running-checks.command-line.006 @rule:cli.run.crashed-gate-is-a-warning @verified @source:src/gandalf/__main__.py#_run_gates @test:tests/test_run.py#test_broken_gate_degrades_to_warn
  Scenario: A gate that crashes is reported as a warning and the run carries on
    Given one gate fails with the error "boom" while running
    When the operator runs gandalf
    Then that gate is shown as WARN with the summary "gate errored: boom"
    And the other gates still report their own results

  @id:running-checks.command-line.007 @rule:cli.run.no-llm-skips-every-llm-use @verified @source:src/gandalf/__main__.py#_drop_llm_gates @test:tests/test_run.py#test_no_llm_drops_the_llm_backed_gates @test:tests/test_run.py#test_a_gate_without_the_marker_is_kept
  Scenario: With --no-llm no LLM-backed gate runs and the summary is skipped
    Given the enabled gates include the LLM-backed gate grill_me and the build gate
    When the operator runs gandalf with --no-llm
    Then grill_me does not run and is listed among the disabled gates
    And the build gate runs
    And the AI summary reads "(LLM summary skipped)"

  @id:running-checks.command-line.008 @rule:cli.run.fix-ignored-for-commit @inferred @source:src/gandalf/__main__.py#_fix_mode
  Scenario: Fixes are not applied when a specific commit is checked
    Given a commit abc1234 in the repository
    When the operator runs gandalf with --commit abc1234 and --fix
    Then the warning "--fix ignored for --commit (throwaway worktree)" is printed
    And no fixer runs and the report lists no fixes
    And the gates still run against the commit

  @id:running-checks.command-line.009 @rule:cli.run.gates-match-detected-languages @inferred @source:src/gandalf/__main__.py#_active_gates
  Scenario: Only gates for the languages in scope run; the rest are listed as skipped
    Given the scope contains only Go files
    And the enabled gates include a Go linter, the Python type checker mypy and a language-neutral secret scanner
    When the operator runs gandalf
    Then the Go linter and the secret scanner run
    And mypy does not run and is listed among the skipped gates

  @id:running-checks.command-line.010 @rule:cli.run.json-owns-stdout @verified @source:src/gandalf/__main__.py#main @test:tests/test_run.py#test_json_leaves_only_the_payload_on_stdout @test:tests/test_run.py#test_without_json_the_scorecard_stays_on_stdout
  Scenario: With --json only the JSON report is written to standard output
    Given a repository that passes every gate
    When the operator runs gandalf with --json
    Then standard output parses as one JSON document whose verdict is "pass"
    And the scorecard and the "JSON report:" line go to standard error

  @id:running-checks.command-line.011 @rule:cli.run.write-baseline-accepts-current-findings @verified @source:src/gandalf/__main__.py#_write_baseline @test:tests/test_run.py#test_stream_applies_baseline_suppression
  Scenario: Writing a baseline accepts today's findings so only new ones fail later runs
    Given a repository with a Python file that does not compile, which fails the build gate
    When the operator runs gandalf with --write-baseline
    Then "Wrote baseline: <path> (1 finding(s))" is printed
    And the run exits with status 0
    And a later run without --write-baseline reports the build gate as pass with no findings
