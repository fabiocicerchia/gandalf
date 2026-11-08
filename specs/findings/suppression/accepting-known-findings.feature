@domain:findings @area:suppression @from:gandalf/suppress
Feature: Accepting known findings
  Lets a team accept findings it has agreed to live with, through standing rules or a baseline snapshot, so only new problems fail the check and the gate itself never has to be turned off.

  Background:
    Given the operator has a repository checked by gandalf

  @id:findings.suppression.005 @rule:findings.suppression.rule-wildcard-matching @verified @source:src/gandalf/suppress.py#_Rule @test:tests/test_suppress.py#test_rule_matching_and_wildcards
  Scenario Outline: A suppression rule mutes the findings that match its gate, rule and path
    Given the ruff gate reports E501 in a.py, F401 in b.py and E501 in tests/t.py
    And the project configuration lists the suppression rule "<rule>"
    When the operator runs gandalf
    Then the ruff gate still reports the findings in <remaining>

    Examples:
      | rule          | remaining              |
      | ruff:E501     | b.py                   |
      | ruff::tests/* | a.py, b.py             |
      | ruff          | nothing                |
      | bandit:E501   | a.py, b.py, tests/t.py |

  @id:findings.suppression.006 @rule:findings.suppression.baseline-accepts-current-findings @verified @source:src/gandalf/__main__.py#_write_baseline @test:tests/test_run.py#test_stream_applies_baseline_suppression @test:tests/test_suppress.py#test_baseline_roundtrip
  Scenario: Writing a baseline accepts today's findings so only new ones fail
    Given the repository has a syntax error that fails the check
    When the operator runs gandalf with --write-baseline
    Then gandalf prints "Wrote baseline: <repo>/.gandalf-baseline.json (1 finding(s))"
    And that same run exits 0
    And later runs report that finding's gate as passing with no findings
    And a finding introduced afterwards still fails the check

  @id:findings.suppression.007 @rule:findings.suppression.baseline-fingerprint-stable @verified @source:src/gandalf/suppress.py#fingerprint @test:tests/test_suppress.py#test_fingerprint_line_insensitive @test:tests/test_findings.py#test_fingerprint_is_stable_for_known_findings @test:tests/test_findings.py#test_fingerprint_vocabulary_is_frozen @test:tests/test_findings.py#test_fingerprint_still_line_insensitive
  Scenario Outline: An accepted finding stays accepted when its line moves or gandalf is upgraded
    Given the baseline accepts ruff E501 "line too long" in a.py at line 1
    When the operator runs gandalf after <change>
    Then the finding is <state>

    Examples:
      | change                                                          | state          |
      | code is added above it, moving it to line 99                    | still accepted |
      | gandalf is upgraded to a release that reads more finding fields | still accepted |
      | its message changes                                             | reported again |

  @id:findings.suppression.008 @rule:findings.suppression.bad-baseline-mutes-nothing @inferred @source:src/gandalf/suppress.py#load_baseline
  Scenario Outline: A missing or unreadable baseline accepts nothing
    Given the ruff gate reports 3 findings
    And the baseline file named with --baseline is <state>
    When the operator runs gandalf
    Then the ruff gate reports all 3 findings
    And the run does not stop with an error

    Examples:
      | state          |
      | absent         |
      | not valid JSON |

  @id:findings.suppression.009 @rule:findings.suppression.baseline-source-precedence @inferred @source:src/gandalf/__main__.py#_baseline_path @questionable
  Scenario Outline: The baseline is taken from --baseline, else the repository default, else the configured path
    Given the repository contains .gandalf-baseline.json
    And the project configuration sets [gandalf.suppress] baseline to "ci/accepted.json"
    When the operator runs gandalf <flags>
    Then findings are accepted from <used>

    Examples:
      | flags                 | used                          |
      | --baseline other.json | other.json                    |
      | without --baseline    | <repo>/.gandalf-baseline.json |
