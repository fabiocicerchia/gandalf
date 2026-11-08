@domain:gate-extensibility @area:unavailable-outcomes @from:gandalf/outcomes
Feature: Reporting gates that could not check the code
  Operators running gandalf on hosts with scanners missing or slow need a gate that could not run to say so plainly, never read as a clean pass, and never move the score.

  Background:
    Given the operator runs gandalf on a repository

  @id:gate-extensibility.unavailable-outcomes.001 @rule:gates.unavailable.reported-amber-and-skipped @verified @source:src/gandalf/outcomes.py#missing_result @test:tests/test_unavailable.py#test_unavailable_is_still_an_amber_gate_result @test:tests/test_lang_gates.py#test_missing_toolchain_warns_and_names_the_binary
  Scenario Outline: A gate whose tool could not run is reported amber and skipped, never passed
    Given the <gate> gate has files in scope
    And <condition>
    When the operator runs a check
    Then the <gate> gate is amber with a score of 0.8
    And its summary reads "<summary>"
    And the gate is marked as not run

    Examples:
      | gate     | condition                                                            | summary                                                             |
      | trivy    | neither a host trivy binary nor the gandalf-tools image is available | trivy unavailable (no host binary or gandalf-tools image) — skipped |
      | licenses | trivy, which the licenses gate runs, is not available                | trivy unavailable (no host binary or gandalf-tools image) — skipped |
      | golang   | the Go tool times out                                                | golang: did not run (timeout or tool unavailable) — skipped         |

  @id:gate-extensibility.unavailable-outcomes.002 @rule:scoring.unavailable.excluded-from-verdict-and-score @verified @source:src/gandalf/report.py#aggregate @test:tests/test_unavailable.py#test_unavailable_gates_are_left_out_of_the_score @test:tests/test_unavailable.py#test_unavailable_gates_do_not_colour_the_verdict
  Scenario Outline: Gates that could not run do not change the overall verdict or score
    Given the ruff gate passed with a score of 1.0
    And the gates <missing> could not run
    When the operator runs a check
    Then the overall verdict is <verdict>
    And the composite score is <score>

    Examples:
      | missing    | verdict | score |
      | trivy      | green   | 100   |
      | a, b and c | green   | 100   |

  @id:gate-extensibility.unavailable-outcomes.003 @rule:scoring.unavailable.real-failure-still-red @verified @source:src/gandalf/report.py#aggregate @test:tests/test_unavailable.py#test_a_gate_that_actually_failed_still_reddens
  Scenario: A real failure still turns the run red when other gates could not run
    Given the ruff gate failed with a score of 0
    And the trivy gate could not run
    When the operator runs a check
    Then the overall verdict is red
    And the composite score is 0

  @id:gate-extensibility.unavailable-outcomes.004 @rule:scoring.unavailable.nothing-ran-is-scoreless @verified @source:src/gandalf/report.py#aggregate @test:tests/test_unavailable.py#test_nothing_ran_at_all_is_amber_and_scoreless @test:tests/test_unavailable.py#test_category_with_nothing_run_reports_no_percentage
  Scenario: When no gate could run, the run is amber with no score earned
    Given every selected gate could not run
    When the operator runs a check
    Then the overall verdict is amber
    And the composite score is 0
    And every category that had nothing run shows no percentage

  @id:gate-extensibility.unavailable-outcomes.005 @rule:gates.unavailable.status-survives-reweighting-and-suppression @verified @source:src/gandalf/outcomes.py#carry_over @test:tests/test_unavailable.py#test_marker_survives_severity_reweighting @test:tests/test_unavailable.py#test_reweighting_keeps_the_duration @test:tests/test_unavailable.py#test_partial_suppression_keeps_the_duration @test:tests/test_unavailable.py#test_full_suppression_keeps_the_metadata_too
  Scenario Outline: A gate's not-run status and run timing survive severity weighting and suppressions
    Given the trivy gate took 1.25 seconds and <state>
    And <adjustment> is in effect
    When the operator runs a check
    Then the reported trivy result still has a duration of 1.25 seconds
    And the trivy gate is still <status>

    Examples:
      | state                        | adjustment                   | status            |
      | could not run                | severity weighting           | marked as not run |
      | reported two vulnerabilities | a suppression rule for trivy | marked as run     |
