@domain:editor-integrations @area:editor-diagnostics @from:extensions/vscode
Feature: Findings inside the editor
  Shows each finding where the developer works, as squiggles and in a findings pane, without letting unchecked gates pass for green.

  Background:
    Given a workspace scan has completed

  @id:editor-integrations.editor-diagnostics.015 @rule:editor.findings.failing-gate-always-visible @verified @source:extensions/vscode/src/parse.ts#normalizeGate @test:extensions/vscode/src/test/parse.test.ts#surfaces a failing gate that reported no findings @test:extensions/vscode/src/test/parse.test.ts#says nothing about a passing gate with no findings
  Scenario Outline: A failing gate with no itemised findings still shows up as one finding
    Given the gate <gate> ended <outcome> with the summary "<summary>" and no findings
    When the developer opens the findings pane
    Then <listing>

    Examples:
      | gate  | outcome | summary                          | listing                                                    |
      | build | red     | build: 1 file(s) fail to compile | one error finding reads "build: 1 file(s) fail to compile" |
      | ruff  | green   | ruff clean                       | nothing is listed for ruff                                 |

  @id:editor-integrations.editor-diagnostics.016 @rule:editor.findings.unassessed-gates-counted @verified @source:extensions/vscode/src/parse.ts#gateStatus @test:extensions/vscode/src/test/parse.test.ts#separates blocked gates from inapplicable ones @test:extensions/vscode/src/test/parse.test.ts#keeps them out of the findings list, but never hides a red gate
  Scenario: Gates that could not run are counted in a notice instead of passing for green
    Given trivy and semgrep reported their tool unavailable
    And dalfox reported it had no target URL
    And the tests gate failed with no itemised findings
    When the developer opens the findings pane
    Then the pane shows "⚠ 2 gate(s) could not run (trivy, semgrep) — run “Gandalf: Check Environment”."
    And the pane shows "Gates not counted: 1 had nothing to assess."
    And trivy, semgrep and dalfox are not listed as findings
    And the failing tests gate is listed

  @id:editor-integrations.editor-diagnostics.017 @rule:editor.findings.editor-excludes-forwarded @verified @source:extensions/vscode/src/storage.ts#excludesFor @test:extensions/vscode/src/test/exclude.test.ts#takes only the unconditionally-enabled entries of an exclude map @test:extensions/vscode/src/test/exclude.test.ts#expands the brace alternation gandalf cannot read @test:extensions/vscode/src/test/exclude.test.ts#drops the depth markers gandalf does not need @test:extensions/vscode/src/test/exclude.test.ts#refuses a pattern that would exclude everything
  Scenario Outline: What the editor already hides is excluded from editor scans
    Given files.exclude enables **/node_modules and **/*.{js,map}, disables **/dist, and conditions **/*.js on a sibling file
    And the extension's own exclude list holds vendor
    And using the editor's excludes is <setting>
    When the developer scans the workspace
    Then gandalf is told to exclude <patterns>

    Examples:
      | setting | patterns                             |
      | on      | vendor, node_modules, *.js and *.map |
      | off     | vendor only                          |
