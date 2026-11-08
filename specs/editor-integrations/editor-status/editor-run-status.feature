@domain:editor-integrations @area:editor-status @from:extensions/vscode
Feature: Run status in the editor
  Tells the developer what a scan is doing and how the code scored, and tells them about failures without nagging.

  Background:
    Given a workspace folder is open

  @id:editor-integrations.editor-status.005 @rule:editor.status.timings-skip-list @verified @source:extensions/vscode/src/commands.ts#showTimings @test:extensions/vscode/src/test/activate.test.ts#says there are no timings yet instead of offering an empty picker
  Scenario Outline: Gate timings let the developer copy a skip list for slow gates
    Given <state>
    When the developer shows gate timings
    Then <outcome>

    Examples:
      | state                                                                               | outcome                                                                                                    |
      | a workspace scan recorded gate durations, and the developer picks semgrep and trivy | the gates are listed slowest first and '[gandalf]\nskip = ["semgrep", "trivy"]' is copied to the clipboard |
      | no workspace scan has run                                                           | the notice "Gandalf: no timings yet — run “Gandalf: Scan Workspace” first." is shown                       |
