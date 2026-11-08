@domain:quality-gates @area:ai-review @from:gandalf/gates
Feature: AI review gates driven by skill playbooks
  Gives reviewers an LLM's read on design readiness, architecture, Well-Architected risk, leanness and security posture, without letting an unavailable model fake a result.

  Background:
    Given the LLM is enabled for the run

  @id:quality-gates.ai-review.001 @rule:ai-review.skill-gates.advisory-never-red @verified @source:src/gandalf/gates/grill_me.py#GrillMeGate @test:tests/test_gandalf.py#test_skill_gate_scores_and_maps_outcome @test:tests/test_gandalf.py#test_llm_skill_gates_discovered
  Scenario Outline: Design, architecture and Well-Architected reviews are green at their threshold and amber below it, never red
    Given the change has a diff in scope
    And the judge scores the "<gate>" review <score>/100
    When the operator runs gandalf
    Then the "<gate>" gate is <colour>
    And the gate is not marked blocking

    Examples:
      | gate                  | score | colour |
      | grill_me              | 80    | green  |
      | grill_me              | 79    | amber  |
      | codebase_architecture | 75    | green  |
      | codebase_architecture | 10    | amber  |
      | well_architected      | 95    | green  |
      | well_architected      | 40    | amber  |

  @id:quality-gates.ai-review.002 @rule:ai-review.quality-gate-review.verdict-blocks @verified @source:src/gandalf/gates/skill_quality_gate.py#QualityGateReviewGate @test:tests/test_gandalf.py#test_skill_gates_discovered @test:tests/test_gandalf.py#test_skill_outcome_coercion
  Scenario Outline: The quality-gate review's GO, REVIEW or NO-GO verdict sets a blocking gate
    Given the quality-gate-review judge returns the verdict <verdict>
    When the operator runs gandalf
    Then the "quality_gate_review" gate is <colour>
    And the scorecard marks it as blocking

    Examples:
      | verdict                            | colour |
      | GO                                 | green  |
      | REVIEW                             | amber  |
      | NO-GO                              | red    |
      | an unrecognised word with score 90 | green  |
      | an unrecognised word with score 50 | red    |

  @id:quality-gates.ai-review.003 @rule:ai-review.advisory-judges-can-turn-red @verified @source:src/gandalf/gates/skill_ruthless_refactor.py#RuthlessRefactorGate @test:tests/test_gandalf.py#test_skill_gates_discovered @questionable
  Scenario Outline: The simplification and security-posture reviews can turn the run red despite being advisory
    Given the judge returns outcome fail with score 45 for the "<gate>" review
    When the operator runs gandalf
    Then the "<gate>" gate is red
    And the overall verdict is red
    And the gate is not marked blocking

    Examples:
      | gate                |
      | ruthless_refactor   |
      | security_assessment |

  @id:quality-gates.ai-review.004 @rule:ai-review.judge-unreachable-not-checked @verified @source:src/gandalf/skillgate.py#SkillGate @test:tests/test_gandalf.py#test_skill_gate_warns_when_judge_unavailable
  Scenario Outline: An unreachable LLM judge leaves an AI review gate not checked, never green
    Given the change has a diff in scope
    And the LLM endpoint refuses connections
    When the operator runs gandalf
    Then the "<gate>" gate is reported as not checked
    And its summary reads "<summary>"

    Examples:
      | gate                  | summary                                                                 |
      | codebase_architecture | codebase_architecture: judge unavailable (connection refused) — skipped |
      | pr_code_summary       | pr_code_summary: skill judge unavailable (connection refused) — skipped |

  @id:quality-gates.ai-review.005 @rule:ai-review.nothing-in-scope-not-checked @verified @source:src/gandalf/skillgate.py#SkillGate @test:tests/test_gandalf.py#test_skill_gate_warns_with_nothing_in_scope
  Scenario: With nothing to judge, a skill review is reported as not checked and the model is not called
    Given there is no diff, no changed file, no --title and no --body
    When the operator runs gandalf
    Then the "grill_me" gate is reported as not checked
    And its summary reads "grill_me: nothing in scope to judge — skipped"
    And no request is sent to the LLM
