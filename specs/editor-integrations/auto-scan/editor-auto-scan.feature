@domain:editor-integrations @area:auto-scan @from:extensions/vscode
Feature: Automatic scanning
  Keeps findings fresh as the developer saves, without flooding the machine with runs or interrupting a scan they asked for.

  Background:
    Given a workspace folder that is a git repository is open

  @id:editor-integrations.auto-scan.004 @rule:editor.autoscan.ignored-saves @verified @source:extensions/vscode/src/storage.ts#scannable @test:extensions/vscode/src/test/activate.test.ts#never lets a report gandalf wrote re-trigger gandalf @test:extensions/vscode/src/test/activate.test.ts#never lets gandalf’s own cache re-trigger gandalf @test:extensions/vscode/src/test/activate.test.ts#leaves a document that is not a file on disk alone @test:extensions/vscode/src/test/activate.test.ts#leaves a file git does not track alone, since gandalf would find nothing
  Scenario Outline: Saves that gandalf would have nothing to scan for never start a run
    Given the scan trigger setting is onSave
    When the developer saves <document>
    Then no scan starts

    Examples:
      | document                                                                          |
      | a file git does not track (untracked.py)                                          |
      | a report gandalf wrote under reports/                                             |
      | gandalf's own .gandalf-cache.json, .gandalf-trend.jsonl or .gandalf-baseline file |
      | an untitled document that is not on disk                                          |
      | a file outside every workspace folder                                             |

  @id:editor-integrations.auto-scan.005 @rule:editor.autoscan.unchanged-file-skipped @verified @source:extensions/vscode/src/scheduler.ts#ContentGuard @test:extensions/vscode/src/test/scheduler.test.ts#sees a file as changed until a scan commits its hash
  Scenario Outline: A file saved without changes since its last successful scan is not rescanned automatically
    Given src/a.py was scanned and the scan succeeded
    And its contents have not changed since
    When <who> asks for a scan of src/a.py
    Then the scan <outcome>

    Examples:
      | who                                               | outcome    |
      | a save of the unchanged file                      | is skipped |
      | the developer, with the Scan Current File command | runs       |
