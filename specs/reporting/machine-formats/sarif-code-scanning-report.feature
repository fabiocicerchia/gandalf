@domain:reporting @area:machine-formats @from:gandalf/sarif
Feature: Publishing findings to code scanning as SARIF
  Lets a CI operator upload gandalf's findings to GitHub code scanning (or any SARIF dashboard) so they appear as ranked, deduplicated alerts on the code instead of lines in a job log.

  Background:
    Given Given the operator runs gandalf with the --sarif option

  @id:reporting.machine-formats.015 @rule:reporting.sarif.findings-become-located-alerts @verified @source:src/gandalf/sarif.py#_collect @test:tests/test_sarif.py#test_levels_and_locations @test:tests/test_sarif.py#test_paths_made_repo_relative @test:tests/test_sarif.py#test_rules_deduped_and_sorted @test:tests/test_sarif.py#test_bandit_findings_are_identified_by_test_id
  Scenario Outline: Each finding becomes an alert at its repository-relative file and line
    Given a gate "<gate>" reports a finding with rule "<rule>" in file "<reported_path>" at line <line>
    And the repository is checked out at "<workdir>"
    When the run completes
    Then the SARIF report holds one alert with rule id "<rule_id>"
    And the alert points at file "<uri>" line <line>
    And the report lists rule "<rule_id>" once among the tool's rules

    Examples:
      | gate   | rule | reported_path       | workdir | line | rule_id     | uri               |
      | ruff   | E501 | a.py                | /work   | 12   | ruff/E501   | a.py              |
      | ruff   | E501 | /src/pkg/a.py       | /src    | 5    | ruff/E501   | pkg/a.py          |
      | bandit | B607 | ./scripts/deploy.py | /work   | 27   | bandit/B607 | scripts/deploy.py |

  @id:reporting.machine-formats.016 @rule:reporting.sarif.alert-level-follows-severity @verified @source:src/gandalf/sarif.py#_collect @test:tests/test_sarif.py#test_levels_and_locations
  Scenario Outline: An alert's level follows the finding's severity, else the gate's outcome
    Given a gate that ended <outcome> reports a located finding with severity "<severity>"
    When the run completes
    Then the alert's level is "<level>"

    Examples:
      | outcome | severity | level   |
      | WARN    | LOW      | note    |
      | WARN    | CRITICAL | error   |
      | FAIL    | MODERATE | warning |
      | FAIL    | (none)   | error   |
      | WARN    | (none)   | warning |
      | PASS    | (none)   | note    |
      | FAIL    | UNKNOWN  | warning |

  @id:reporting.machine-formats.017 @rule:reporting.sarif.rules-ranked-by-highest-severity @verified @source:src/gandalf/sarif.py#_bump_severity @test:tests/test_sarif.py#test_security_severity_on_rules @questionable
  Scenario Outline: Each rule is ranked by the most severe finding raised under it
    Given rule "<rule_id>" has located findings with severities <severities> on a gate that ended <outcome>
    When the run completes
    Then rule "<rule_id>" carries a security-severity of <score>

    Examples:
      | rule_id          | severities    | outcome | score |
      | bandit/B101      | LOW           | WARN    | 2.0   |
      | semgrep/sqli     | LOW, CRITICAL | WARN    | 9.0   |
      | ruff/E501        | (none)        | FAIL    | 7.0   |
      | eslint/no-unused | (none)        | WARN    | 4.0   |

  @id:reporting.machine-formats.018 @rule:reporting.sarif.no-alert-without-location @verified @source:src/gandalf/sarif.py#_collect @test:tests/test_sarif.py#test_results_without_a_location_are_left_out @test:tests/test_sarif.py#test_the_count_of_dropped_findings_is_recorded @test:tests/test_sarif.py#test_passing_gate_emits_nothing @test:tests/test_sarif.py#test_levels_and_locations
  Scenario Outline: Findings that cannot be placed in a file are counted, never uploaded as alerts
    Given <case>
    When the run completes
    Then every alert in the SARIF report points at a file
    And the report records <count> findings without location

    Examples:
      | case                                                                 | count |
      | a gate that failed with a compile error and named no file            | 1     |
      | a gate reports a repository-level finding with no file               | 1     |
      | a gate that warned "codespell: unavailable" and reported no findings | 0     |
      | a gate that passed with no findings                                  | 0     |

  @id:reporting.machine-formats.019 @rule:reporting.sarif.stable-alert-fingerprints @verified @source:src/gandalf/suppress.py#fingerprint @test:tests/test_sarif.py#test_partial_fingerprints_present_and_stable
  Scenario Outline: The same finding keeps the same alert identity across runs
    Given a finding "long" from gate "ruff" with rule "E501" in file "a.py" was reported at line <first_line> in the previous run
    When the operator runs gandalf again and the finding is now at line <second_line>
    Then the alert carries the same gandalf/v1 fingerprint in both reports

    Examples:
      | first_line | second_line |
      | 12         | 12          |
      | 12         | 40          |

  @id:reporting.machine-formats.020 @rule:reporting.sarif.rule-ids-within-upload-limit @verified @source:src/gandalf/sarif.py#_rule_id @test:tests/test_sarif.py#test_over_long_rule_ids_are_truncated_and_stay_distinct
  Scenario: Over-long rule ids are shortened so the upload is accepted, and stay distinct
    Given a gate "tool" reports two findings whose rule ids are 400 characters long and differ only in the last character
    When the run completes
    Then the SARIF report lists two separate rules
    And no rule id is longer than 255 characters

  @id:reporting.machine-formats.021 @rule:reporting.sarif.distinct-gandalf-alert-set @verified @source:src/gandalf/sarif.py#to_sarif @test:tests/test_sarif.py#test_automation_details_category @test:tests/test_sarif.py#test_shape_and_serializable
  Scenario Outline: gandalf's alerts are published as their own SARIF 2.1.0 tool run
    Given gandalf version "<version>" is running
    When the run completes
    Then the report declares SARIF version 2.1.0
    And its single run names the tool "gandalf" with version "<version>"
    And the run's automation id is "gandalf"

    Examples:
      | version |
      | 1.4.0   |
