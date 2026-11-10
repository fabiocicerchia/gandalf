@domain:running-checks @area:scheduling @from:gandalf/schedule
Feature: Starting the heaviest gates first
  Operators running many gates under a concurrency cap get the shortest overall scan because the slowest gates start immediately and quick ones fill in behind them.

  Background:
    Given the operator runs gandalf with --debug

  @id:running-checks.scheduling.004 @rule:scheduling.order.heaviest-first @verified @source:src/gandalf/schedule.py#order @test:tests/test_schedule.py#test_known_heavy_gates_go_first @test:tests/test_schedule.py#test_ordering_keeps_every_gate @test:tests/test_schedule.py#test_an_unknown_gate_gets_the_default
  Scenario: Gates known to be slow start before quick linters
    Given the selected gates are bandit, ruff, trivy, codeql and yamllint
    And no earlier run has recorded how long any gate took
    When the operator runs a check
    Then the debug log reports the gate order as "priors only (no cache history)"
    And the gates are started in the order codeql, trivy, bandit, yamllint, ruff
    And all five gates run

  @id:running-checks.scheduling.005 @rule:scheduling.estimate.measured-wins @verified @source:src/gandalf/schedule.py#cost @test:tests/test_schedule.py#test_a_measurement_beats_the_prior @test:tests/test_schedule.py#test_a_gate_may_declare_its_own_cost
  Scenario Outline: A gate's measured duration from the last cached run outranks any declared or built-in estimate
    Given result caching is enabled with --cache and the scanned files have changed since the last cached run
    And gate <gate_a> declares a cost of <declared_a> seconds and last took <measured_a> seconds
    And gate <gate_b> declares no cost and last took <measured_b> seconds
    When the operator runs a check
    Then the debug log reports the gate order as "measured + priors"
    And <first> is started before <second>

    Examples:
      | gate_a | declared_a | measured_a | gate_b | measured_b | first | second |
      | custom | 999        | 0.1        | ruff   | 3          | ruff  | custom |
      | codeql | none       | 2          | tests  | 400        | tests | codeql |

  @id:running-checks.scheduling.006 @rule:scheduling.estimate.plugin-declared-cost @verified @source:src/gandalf/schedule.py#cost @test:tests/test_schedule.py#test_a_gate_may_declare_its_own_cost
  Scenario: A third-party gate can declare its own expected cost
    Given a third-party gate "custom" declares a cost of 999 seconds
    And no earlier run has recorded how long any gate took
    And ruff is also selected
    When the operator runs a check
    Then custom is started before ruff

  @id:running-checks.scheduling.007 @rule:scheduling.estimate.invalid-cost-tolerated @verified @source:src/gandalf/schedule.py#cost @test:tests/test_schedule.py#test_a_nonsense_cost_is_scheduled_not_rejected
  Scenario: A gate declaring a nonsensical cost still runs
    Given a gate declares its cost as "soon"
    When the operator runs a check
    Then the run does not fail on the bad cost
    And the gate is scheduled using its built-in estimate, or 10 seconds when it has none

  @id:running-checks.scheduling.008 @rule:scheduling.order.reproducible @verified @source:src/gandalf/schedule.py#order @test:tests/test_schedule.py#test_ties_break_by_name_so_the_order_is_reproducible
  Scenario: Gates with equal estimates always start in name order
    Given the selected gates zulu, alpha and mike have no recorded, declared or built-in estimate
    When the operator runs a check
    Then the gates are started in the order alpha, mike, zulu
    And two runs over the same repository log the same gate order
