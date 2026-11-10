@domain:reporting @area:machine-formats @from:gandalf/console
Feature: Piping the JSON report from the command line
  Lets operators and CI scripts pipe gandalf's JSON report straight into a parser without the human scorecard getting in the way.

  Background:
    Given a repository with gandalf checks configured

  @id:reporting.machine-formats.001 @rule:reporting.json.stdout-carries-only-the-payload @verified @source:src/gandalf/console.py#divert_human_output @test:tests/test_run.py#test_json_leaves_only_the_payload_on_stdout @test:tests/test_run.py#test_without_json_the_scorecard_stays_on_stdout
  Scenario Outline: With JSON output requested, standard output carries only the JSON report and the human lines move to standard error
    Given the operator has chosen the output mode <mode>
    When the operator runs a gandalf check
    Then standard output contains <stdout>
    And the human-readable lines such as "JSON report: <path>" appear on <human_stream>

    Examples:
      | mode                | stdout                                                                     | human_stream    |
      | --json              | only the JSON report, which parses as a whole document                     | standard error  |
      | default (no --json) | the scorecard and the "JSON report:" line                                  | standard output |
