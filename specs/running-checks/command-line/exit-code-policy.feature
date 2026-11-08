@domain:running-checks @area:command-line @from:gandalf/report
Feature: Failing the build on the verdict
  Lets operators choose which verdicts and scores fail the build, without changing what the scorecard shows.

  Background:
    Given a repository with gates enabled

  @id:running-checks.command-line.015 @rule:running-checks.exit-policy.verdict-and-floor-decide-exit-code @verified @source:src/gandalf/report.py#decide @test:tests/test_report.py#test_decide
  Scenario Outline: The run fails on a red verdict, on amber when fail-on is warn, or when the score is below min-score
    Given the fail-on policy is <fail_on> and the min-score is <min_score>
    And the run's verdict is <verdict> with a score of <score>
    When the operator runs a check
    Then gandalf exits with status <exit>
    And the JSON report records passed as <passed> with the reason "<reason>"

    Examples:
      | fail_on | min_score | verdict | score | exit | passed | reason                       |
      | fail    | 0         | GREEN   | 100   | 0    | true   | policy satisfied             |
      | fail    | 0         | AMBER   | 80    | 0    | true   | policy satisfied             |
      | fail    | 0         | RED     | 50    | 1    | false  | a gate failed                |
      | warn    | 0         | AMBER   | 80    | 1    | false  | a gate warned (fail-on=warn) |
      | fail    | 90        | GREEN   | 80    | 1    | false  | score 80 below min-score 90  |
      | fail    | 90        | GREEN   | 95    | 0    | true   | policy satisfied             |
