@domain:editor-integrations @area:editor-history @from:extensions/vscode
Feature: Score history in the editor
  Shows a developer whether the repository's score is improving commit by commit, and lets them score any recent commit.

  Background:
    Given a workspace folder that is a git repository is open

  @id:editor-integrations.editor-history.004 @rule:editor.history.score-per-commit @verified @source:extensions/vscode/src/commands.ts#showHistory @test:extensions/vscode/src/test/history.test.ts#signs the change against the previous score @test:extensions/vscode/src/test/history.test.ts#takes the newest line for a commit scanned more than once
  Scenario: The history lists recent commits with their score and change, and marks unscanned ones
    Given the trend log scored commit a1b2c3d at 80 and its later commit e4f5a6b at 85
    And commit 9d8e7f6 has never been scanned
    When the developer shows the score history
    Then e4f5a6b is listed as "85/100  +5"
    And a1b2c3d is listed as "80/100"
    And 9d8e7f6 is listed as "— not scanned"
    And the title shows a sparkline "over 2 scanned commit(s) of" the number of commits listed, at most the last 40
