@domain:reporting @area:machine-formats @from:gandalf/junit
Feature: Publishing gate results as a JUnit test report
  Lets CI operators see each gandalf gate in their CI system's existing test panel (Jenkins, GitLab, CodeBuild, ...) with no plugin, so a failing gate reads like a failing test.

  Background:
    Given a repository whose gandalf run evaluated the gates "ruff", "bandit" and "gitleaks"

  @id:reporting.machine-formats.002 @rule:reporting.junit.one-testcase-per-gate @verified @source:src/gandalf/junit.py#to_junit @test:tests/test_junit.py#test_shape_and_parseable
  Scenario: Every gate appears as one test case in a single gandalf suite
    Given "ruff" failed, "bandit" warned and "gitleaks" passed
    When the operator runs gandalf with --junit
    Then the JUnit file holds one test suite named "gandalf"
    And the suite reports 3 tests and 1 failure, with 0 errors and 0 skipped
    And each gate is a test case named after the gate, in class "gandalf"

  @id:reporting.machine-formats.003 @rule:reporting.junit.failed-gate-is-failed-test @verified @source:src/gandalf/junit.py#_testcase @test:tests/test_junit.py#test_fail_becomes_failure_element
  Scenario: A failed gate shows as a failing test carrying its summary and findings
    Given the "ruff" gate failed with summary "ruff: 2 findings"
    And its findings include "a.py:12 E501 long"
    When the operator runs gandalf with --junit
    Then the "ruff" test case is marked as failed
    And the failure message reads "ruff: 2 findings"
    And the failure details list the summary followed by one line per finding, including "long"

  @id:reporting.machine-formats.004 @rule:reporting.junit.warning-gate-passes-with-note @verified @source:src/gandalf/junit.py#_testcase @test:tests/test_junit.py#test_warn_stays_passing_with_system_out @questionable
  Scenario: A warning gate stays a passing test with its notes attached
    Given the "bandit" gate warned with summary "1 issue" and the finding "assert"
    When the operator runs gandalf with --junit
    Then the "bandit" test case is not marked as failed
    And its output note contains "1 issue" and "assert"

  @id:reporting.machine-formats.005 @rule:reporting.junit.passed-gate-is-clean-test @verified @source:src/gandalf/junit.py#_testcase @test:tests/test_junit.py#test_passing_gate_has_no_failure_or_system_out
  Scenario: A passed gate is a clean passing test with no notes
    Given the "gitleaks" gate passed with summary "clean"
    When the operator runs gandalf with --junit
    Then the "gitleaks" test case is not marked as failed
    And it carries no output note

  @id:reporting.machine-formats.006 @rule:reporting.junit.gate-duration-as-test-time @inferred @source:src/gandalf/junit.py#_testcase
  Scenario Outline: A gate's run time is reported as its test time when known
    Given the "ruff" gate took <duration> seconds to run
    When the operator runs gandalf with --junit
    Then the "ruff" test case shows a time of <time>

    Examples:
      | duration     | time          |
      | 1.23456      | 1.235         |
      | not recorded | no time shown |

  @id:reporting.machine-formats.007 @rule:reporting.junit.written-only-on-request @inferred @source:src/gandalf/outputs.py#write_outputs
  Scenario Outline: The JUnit report is written only when asked, to the chosen or default path
    Given the run writes its reports to the "reports" folder
    When the operator runs gandalf <flag>
    Then <outcome>

    Examples:
      | flag                              | outcome                                                                                               |
      | without --junit                   | no JUnit file is written                                                                              |
      | with --junit                      | a JUnit file named <run-name>.junit.xml is written in "reports" and "JUnit report: <path>" is printed |
      | with --junit ci/gandalf.junit.xml | the JUnit file is written to ci/gandalf.junit.xml and "JUnit report: ci/gandalf.junit.xml" is printed |
