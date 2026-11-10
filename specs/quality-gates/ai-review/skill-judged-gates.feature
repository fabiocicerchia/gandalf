@domain:quality-gates @area:ai-review @from:gandalf/skills
Feature: Judging a change against an embedded review playbook
  Gives operators advisory, LLM-judged gates (quality-gate review, ruthless refactor, PR summary, security assessment) whose verdicts read the same as any other gate on the scorecard.

  Background:
    Given gandalf ships the review playbooks pr-code-summarizer, quality-gate-review, ruthless-refactor and security-assessment
    And a model endpoint is configured for AI review

  @id:quality-gates.ai-review.007 @rule:ai-review.skill-gates.verdict-word-decides-outcome @verified @source:src/gandalf/skills.py#_coerce_outcome @test:tests/test_gandalf.py#test_skill_outcome_coercion
  Scenario Outline: The model's verdict word decides the gate outcome, whatever the score
    Given the model judges the change with verdict "<verdict>" and score <score>
    When the operator runs gandalf
    Then the skill gate shows outcome <outcome>
    And the skill gate's score is <score>/100

    Examples:
      | verdict | score | outcome |
      | pass    | 0     | PASS    |
      | GO      | 40    | PASS    |
      | warn    | 95    | WARN    |
      | REVIEW  | 90    | WARN    |
      | fail    | 99    | FAIL    |
      | no-go   | 90    | FAIL    |
      | NO_GO   | 90    | FAIL    |

  @id:quality-gates.ai-review.008 @rule:ai-review.skill-gates.unknown-verdict-uses-score-bands @verified @source:src/gandalf/skills.py#_coerce_outcome @test:tests/test_gandalf.py#test_skill_outcome_coercion
  Scenario Outline: An unrecognised verdict is graded by its score
    Given the model judges the change with verdict "looks fine" and score <score>
    When the operator runs gandalf
    Then the skill gate shows outcome <outcome>

    Examples:
      | score | outcome |
      | 90    | PASS    |
      | 80    | PASS    |
      | 70    | WARN    |
      | 60    | WARN    |
      | 50    | FAIL    |

  @id:quality-gates.ai-review.009 @rule:ai-review.skill-gates.score-clamped-to-0-100 @inferred @source:src/gandalf/skills.py#judge
  Scenario Outline: A skill gate's score always reads between 0 and 100
    Given the model judges the change with verdict "pass" and score "<reported>"
    When the operator runs gandalf
    Then the skill gate's score is <shown>/100

    Examples:
      | reported  | shown |
      | 150       | 100   |
      | -20       | 0     |
      | 72.6      | 73    |
      | excellent | 0     |

  @id:quality-gates.ai-review.010 @rule:ai-review.skill-gates.unreachable-judge-not-checked @inferred @source:src/gandalf/skills.py#judge @questionable
  Scenario Outline: An unreachable or unintelligible model leaves the skill gate not checked instead of failing the run
    Given the model endpoint <condition>
    When the operator runs gandalf
    Then the run completes
    And the skill gate is reported as not checked with a summary containing "skill judge unavailable" and "skipped"
    And the skill gate does not count towards the overall verdict

    Examples:
      | condition                                    |
      | is unreachable                               |
      | replies with prose that holds no JSON object |

  @id:quality-gates.ai-review.011 @rule:ai-review.skill-gates.tolerant-verdict-reply @verified @source:src/gandalf/skills.py#parse_json @test:tests/test_gandalf.py#test_skill_json_parsing
  Scenario Outline: A verdict wrapped in markdown fences or surrounding prose is still read
    Given the model replies with its JSON verdict <wrapping>
    When the operator runs gandalf
    Then the skill gate shows the outcome, score and summary from that verdict

    Examples:
      | wrapping                      |
      | inside a ```json fenced block |
      | between sentences of prose    |
      | as bare JSON                  |

  @id:quality-gates.ai-review.012 @rule:ai-review.skill-gates.findings-capped-at-twelve @inferred @source:src/gandalf/skills.py#judge
  Scenario: A skill gate lists at most twelve non-empty findings
    Given the model's verdict lists 15 findings, two of them blank
    When the operator runs gandalf
    Then the skill gate shows 12 findings
    And no blank finding is shown

  @id:quality-gates.ai-review.013 @rule:ai-review.skill-gates.playbook-from-gandalf-not-reviewed-repo @verified @source:src/gandalf/skills.py#load_skill @test:tests/test_gandalf.py#test_skill_playbooks_load
  Scenario: The review playbook comes from gandalf itself, never from the repository under review
    Given the repository under review contains its own skills/quality-gate-review/SKILL.md
    When the operator runs gandalf against a specific commit
    Then the quality-gate review is judged with the playbook shipped with gandalf
    And the playbook's YAML front matter is not sent as part of the rubric
