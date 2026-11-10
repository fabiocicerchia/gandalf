@domain:findings @area:scoring @from:gandalf/report
Feature: Scoring a run into one traffic light
  Gives developers and reviewers one Red/Amber/Green verdict and a 0-100 score per run, plus one per concern, so they can tell at a glance whether a change is fit to merge.

  Background:
    Given a repository with gates enabled

  @id:findings.scoring.001 @rule:findings.scoring.worst-gate-outcome-sets-verdict @verified @source:src/gandalf/report.py#aggregate @test:tests/test_gandalf.py#test_aggregate_rag @test:tests/test_report.py#test_aggregate_edges
  Scenario Outline: The run's verdict is the worst outcome of the gates that ran
    Given the gates that ran ended <gate outcomes>
    When the developer runs a check
    Then the overall verdict is <verdict>

    Examples:
      | gate outcomes                    | verdict |
      | GREEN, GREEN                     | GREEN   |
      | GREEN, AMBER                     | AMBER   |
      | GREEN, RED                       | RED     |
      | AMBER, RED                       | RED     |
      | GREEN, RED from an advisory gate | RED     |

  @id:findings.scoring.002 @rule:findings.scoring.composite-score-is-mean-of-gate-scores @verified @source:src/gandalf/report.py#aggregate @test:tests/test_gandalf.py#test_aggregate_score
  Scenario Outline: The run's score is the average of the scores of the gates that ran, out of 100
    Given the gates that ran scored <gate scores>
    When the developer runs a check
    Then the run's score is <score>

    Examples:
      | gate scores   | score |
      | 1.0           | 100   |
      | 1.0, 0.0      | 50    |
      | 0.3, 1.0, 0.7 | 67    |

  @id:findings.scoring.003 @rule:findings.scoring.unavailable-gates-do-not-count @verified @source:src/gandalf/report.py#aggregate @test:tests/test_unavailable.py#test_unavailable_gates_are_left_out_of_the_score @test:tests/test_unavailable.py#test_unavailable_gates_do_not_colour_the_verdict @test:tests/test_unavailable.py#test_a_gate_that_actually_failed_still_reddens
  Scenario: A gate that could not run changes neither the verdict nor the score
    Given ruff and mypy ran and passed with a score of 1.0
    And trivy, osv and kics could not run because their tools are not installed
    When the developer runs a check
    Then the overall verdict is GREEN
    And the run's score is 100
    And the JSON report marks trivy, osv and kics as unavailable

  @id:findings.scoring.004 @rule:findings.scoring.nothing-ran-is-amber-with-no-score @verified @source:src/gandalf/report.py#aggregate @test:tests/test_unavailable.py#test_nothing_ran_at_all_is_amber_and_scoreless @test:tests/test_report.py#test_aggregate_edges @test:tests/test_gandalf.py#test_aggregate_rag
  Scenario Outline: A run in which no gate could run is amber with a score of 0
    Given <situation>
    When the developer runs a check
    Then the overall verdict is AMBER
    And the run's score is 0

    Examples:
      | situation                     |
      | no gate applies to the change |
      | every gate's tool is missing  |

  @id:findings.scoring.005 @rule:findings.scoring.category-light-and-percentage @verified @source:src/gandalf/report.py#group_outcome_and_pct @test:tests/test_unavailable.py#test_category_with_nothing_run_reports_no_percentage @test:tests/test_unavailable.py#test_html_render_labels_them_not_run
  Scenario Outline: Each concern shows the worst outcome and average score of its gates, or 'not run' when none of them ran
    Given the Dependencies concern holds <gates>
    When the developer runs a check
    Then the Dependencies concern shows <light> and <percentage>

    Examples:
      | gates                                         | light | percentage |
      | trivy passed with 1.0                         | GREEN | 100%       |
      | trivy passed with 1.0 and osv failed with 0.0 | RED   | 50%        |
      | only trivy, which could not run               | AMBER | not run    |

  @id:findings.scoring.006 @rule:findings.scoring.gates-grouped-by-concern @inferred @source:src/gandalf/report.py#category_of @questionable
  Scenario Outline: Each gate is reported under the concern it checks, and an unknown gate goes under Other
    Given the run includes the <gate> gate
    When the developer runs a check
    Then the scorecard and the JSON report list <gate> under <category>

    Examples:
      | gate                                                      | category     |
      | gitleaks                                                  | Security     |
      | trivy                                                     | Dependencies |
      | ruff                                                      | Code quality |
      | a third-party gate that declares the category Performance | Performance  |
      | a third-party gate that declares no category              | Other        |
