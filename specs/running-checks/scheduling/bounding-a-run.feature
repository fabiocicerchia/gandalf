@domain:running-checks @area:scheduling @from:gandalf/gandalf
Feature: Bounding how hard and how long a run works
  Lets operators cap how many gates run at once and how long a run and each gate's tools may take, so a laptop or CI runner is not swamped.

  @id:running-checks.scheduling.001 @rule:cli.scheduling.concurrency-cap-precedence @verified @source:src/gandalf/__main__.py#_resolve_concurrency @test:tests/test_run.py#test_resolve_concurrency_precedence @test:tests/test_run.py#test_concurrency_is_bounded @test:tests/test_run.py#test_unbounded_runs_all_at_once
  Scenario Outline: The concurrency cap comes from the flag, then the environment, then the config, then the CPU count
    Given --concurrency is <flag>
    And GANDALF_CONCURRENCY is <env>
    And the project configuration sets concurrency to <config>
    When the operator runs gandalf
    Then at most <cap> gates run at the same time

    Examples:
      | flag  | env   | config | cap                     |
      | 5     | unset | 7      | 5                       |
      | unset | 4     | 7      | 4                       |
      | unset | unset | 7      | 7                       |
      | unset | unset | unset  | the machine's CPU count |
      | 0     | unset | unset  | unbounded               |

  @id:running-checks.scheduling.002 @rule:cli.scheduling.run-deadline-precedence @verified @source:src/gandalf/__main__.py#_resolve_deadline @test:tests/test_run.py#test_resolve_deadline_precedence @test:tests/test_run.py#test_past_the_deadline_a_tool_is_not_started
  Scenario Outline: A run has no time limit unless the flag, the environment or the config sets one
    Given --deadline is <flag>
    And GANDALF_DEADLINE is <env>
    And the project configuration sets deadline to <config>
    When the operator runs gandalf
    Then the run's time budget is <budget>
    And tools that would start after the budget runs out are reported as not run

    Examples:
      | flag  | env   | config | budget      |
      | unset | unset | unset  | unlimited   |
      | 90    | unset | 300    | 90 seconds  |
      | unset | 120   | 300    | 120 seconds |
      | unset | unset | 300    | 300 seconds |

  @id:running-checks.scheduling.003 @rule:cli.scheduling.per-gate-timeout @verified @source:src/gandalf/__main__.py#_gate_timeout @test:tests/test_run.py#test_gate_timeout_resolution @test:tests/test_run.py#test_per_gate_timeout_visible_in_run
  Scenario: A gate's own timeout overrides the default timeout
    Given the timeouts configuration sets default to 60 and semgrep to 300
    When the operator runs gandalf
    Then semgrep's tools may run for up to 300 seconds
    And ruff's tools may run for up to 60 seconds
