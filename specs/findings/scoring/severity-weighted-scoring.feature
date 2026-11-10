@domain:findings @area:scoring @from:gandalf/severity
Feature: Severity-weighted gate scoring
  Lets an operator make one critical vulnerability weigh more on the overall score than a handful of minor findings, without changing any gate's traffic light.

  Background:
    Given a repository with a gate whose findings report severities, such as trivy

  @id:findings.scoring.007 @rule:findings.scoring.severity-weight-is-opt-in @inferred @source:src/gandalf/__main__.py#_score
  Scenario Outline: Severity weighting applies only when the operator turns it on
    Given the trivy gate scored 0.90 by finding count and reported one CRITICAL finding
    When the operator runs gandalf <mode>
    Then the trivy gate's score in the report is <score>

    Examples:
      | mode                                                            | score |
      | without --severity-weight and without [gandalf.severity] weight | 0.9   |
      | with --severity-weight                                          | 0.6   |
      | with [gandalf.severity] weight = true in the project config     | 0.6   |

  @id:findings.scoring.008 @rule:findings.scoring.severity-weighted-score @verified @source:src/gandalf/severity.py#score @test:tests/test_severity.py#test_score_orders_by_severity @test:tests/test_severity.py#test_reweight_preserves_outcome_and_untouched_gates
  Scenario Outline: A gate's score falls with the severity of its findings, flooring at zero
    Given severity weighting is on
    And the trivy gate reported <findings>
    When the operator runs gandalf
    Then the trivy gate's score in the report is <score>

    Examples:
      | findings                          | score |
      | one CRITICAL finding              | 0.6   |
      | five LOW findings                 | 0.8   |
      | one CRITICAL and one LOW finding  | 0.56  |
      | three CRITICAL findings           | 0.0   |
      | one finding rated UNKNOWN         | 0.9   |
      | one INFO finding                  | 0.99  |
      | one semgrep finding rated WARNING | 0.9   |

  @id:findings.scoring.009 @rule:findings.scoring.unrated-gates-keep-their-score @verified @source:src/gandalf/severity.py#reweight @test:tests/test_severity.py#test_reweight_preserves_outcome_and_untouched_gates @test:tests/test_explain_score.py#test_no_note_when_reweighting_changed_nothing
  Scenario: A gate whose findings carry no severity keeps the score it gave itself
    Given severity weighting is on
    And the ruff gate scored 0.30 and its findings report no severity
    When the operator runs gandalf
    Then the ruff gate's score in the report is 0.3
    And the score explanation carries no severity-weighted note for ruff

  @id:findings.scoring.010 @rule:findings.scoring.severity-weight-keeps-traffic-light @verified @source:src/gandalf/severity.py#reweight @test:tests/test_severity.py#test_reweight_preserves_outcome_and_untouched_gates @test:tests/test_unavailable.py#test_reweighting_keeps_the_duration
  Scenario: Severity weighting never changes a gate's traffic light or its blocking status
    Given severity weighting is on
    And the trivy gate is Amber and blocking, scored 0.90, with one CRITICAL and one LOW finding
    When the operator runs gandalf
    Then the trivy gate is still Amber
    And the trivy gate is still blocking
    And the trivy gate's score is lower than 0.90
    And the trivy gate's findings and summary are unchanged

  @id:findings.scoring.011 @rule:findings.scoring.explain-shows-gate-own-score @verified @source:src/gandalf/severity.py#reweight @test:tests/test_explain_score.py#test_shows_the_gates_own_score_when_severity_reweighted
  Scenario: The score explanation shows what the gate itself scored next to its weighted score
    Given severity weighting is on
    And the trivy gate scored 0.90 and reported one CRITICAL and one HIGH finding
    When the operator runs gandalf with --explain-score
    Then the explanation shows "gate scored 0.90" for trivy
    And the explanation marks trivy's contribution as severity-weighted

  @id:findings.scoring.012 @rule:findings.scoring.severity-weight-ignores-suppressed @inferred @source:src/gandalf/__main__.py#_score
  Scenario: Suppressed findings do not count toward a gate's severity weight
    Given severity weighting is on
    And the trivy gate reported one CRITICAL and one LOW finding
    And the CRITICAL finding is accepted by a suppression rule
    When the operator runs gandalf
    Then the trivy gate's score in the report is 0.96
