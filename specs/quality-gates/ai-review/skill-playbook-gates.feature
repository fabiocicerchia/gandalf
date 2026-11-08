@domain:quality-gates @area:ai-review @from:gandalf/skillgate
Feature: Judging a change against a skill playbook
  Gives teams advisory, LLM-judged design and architecture feedback (grill-me, codebase architecture, well-architected) that flags friction in amber without ever blocking a build.

  Background:
    Given the repository has the advisory skill gates grill_me, codebase_architecture and well_architected enabled
    And an LLM judge is configured

  @id:quality-gates.ai-review.006 @rule:ai-review.skill-gates.judge-findings-reported @verified @source:src/gandalf/skillgate.py#_normalize_findings @test:tests/test_gandalf.py#test_normalize_findings_maps_keys @test:tests/test_gandalf.py#test_skill_gate_scores_and_maps_outcome
  Scenario: The judge's findings and summary appear in the gate's results
    Given the change under evaluation has a diff in scope
    And the judge reports a high-severity finding "No DR" with detail "add backups" at "infra.tf:3" and the summary "gaps"
    When the operator runs gandalf
    Then the well_architected gate lists a finding "No DR" with severity "high", description "add backups" and location "infra.tf:3"
    And the well_architected gate shows the judge summary "gaps"
    And at most 20 judge findings are listed and findings with no text are dropped
