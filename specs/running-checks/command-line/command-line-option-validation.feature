@domain:running-checks @area:command-line @from:gandalf/cli
Feature: Validating command-line options
  Operators and CI pipelines get an immediate usage error for a malformed invocation, so gandalf never runs a scan they did not ask for.

  Background:
    Given gandalf is installed and run from a git repository

  @id:running-checks.command-line.001 @rule:cli.scope.staged-and-commit-exclusive @inferred @source:src/gandalf/cli.py#build_parser
  Scenario: Staged changes and a specific commit cannot be evaluated in the same run
    Given the operator wants to evaluate a run's scope
    When the operator runs gandalf with both --staged and --commit 1a2b3c4
    Then gandalf refuses with a usage error saying --staged is not allowed with --commit
    And no gate is run and no report is written
    And the exit code is 2

  @id:running-checks.command-line.002 @rule:cli.policy.fail-on-choices @inferred @source:src/gandalf/cli.py#build_parser
  Scenario Outline: The failing threshold accepts only fail or warn
    Given the operator wants to tighten or keep the run's failure policy
    When the operator runs gandalf with --fail-on <value>
    Then <result>

    Examples:
      | value | result                                                                                |
      | fail  | the run proceeds and only a failing gate fails the run                                |
      | warn  | the run proceeds and a warning gate also fails the run                                |
      | error | gandalf refuses with a usage error listing the choices 'fail' and 'warn', exit code 2 |

  @id:running-checks.command-line.003 @rule:cli.options.numeric-values-must-be-integers @inferred @source:src/gandalf/cli.py#build_parser @questionable
  Scenario Outline: Numeric options refuse values that are not whole numbers
    Given the operator passes a value to a numeric option
    When the operator runs gandalf with <option> <value>
    Then gandalf refuses with a usage error saying <value> is an invalid int value for <option>
    And the exit code is 2

    Examples:
      | option        | value |
      | --min-score   | high  |
      | --concurrency | four  |
      | --deadline    | 1.5   |
      | --pr          | abc   |
