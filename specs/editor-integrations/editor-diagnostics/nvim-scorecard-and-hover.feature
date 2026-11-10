@domain:editor-integrations @area:editor-diagnostics @from:extensions/nvim
Feature: Reading the scorecard and dependency details in Neovim
  Gives a Neovim user the run's verdict and the story behind a dependency without leaving the editor, and never lets an unchecked gate pass for a clean one.

  Background:
    Given the gandalf Neovim plugin is set up in a git project

  @id:editor-integrations.editor-diagnostics.009 @rule:nvim.scorecard.verdict-and-gates @verified @source:extensions/nvim/lua/gandalf/ui.lua#M.report_lines @test:extensions/nvim/tests/ui_spec.lua#leads with the verdict word, the score and the scope @test:extensions/nvim/tests/ui_spec.lua#groups the gates under the categories the report gave them @test:extensions/nvim/tests/ui_spec.lua#counts the findings and spreads the summary over its own lines
  Scenario: The scorecard leads with the verdict, the score and the scope
    Given the last scan scored 71/100 with an amber verdict on the working tree
    And ruff warned with one finding and the summary "ruff: 2 issue(s)" under "Code quality" and trivy passed under "Security"
    And the report has a two-line summary
    When the developer runs :GandalfReport
    Then a window titled "Gandalf scorecard" opens
    And its first line reads "AMBER · 71/100    scope: working-tree"
    And ruff is listed under "Code quality" and trivy under "Security"
    And it states "1 finding(s)" followed by the summary lines

  @id:editor-integrations.editor-diagnostics.010 @rule:nvim.scorecard.unchecked-gates-shown-apart @verified @source:extensions/nvim/lua/gandalf/core/gates.lua#M.gate_status @test:extensions/nvim/tests/ui_spec.lua#never lets a green board mean a gate that could not run @test:extensions/nvim/tests/ui_spec.lua#names what had nothing to assess separately from what was blocked @test:extensions/nvim/tests/ui_spec.lua#keeps a gate that assessed nothing out of the category listing @test:extensions/nvim/tests/core_spec.lua#separates what could not run from what had nothing to do @test:extensions/nvim/tests/init_spec.lua#splits out the gates that assessed nothing, so green never means unchecked
  Scenario: Gates that could not run or had nothing to assess are named apart from real results
    Given the last scan's semgrep gate warned with "semgrep: unavailable" and no findings
    And the dalfox gate warned with "dalfox: no target URL — skipped" and no findings
    When the developer runs :GandalfReport
    Then semgrep is not listed among the gates of its category
    And a section "Could not run (install the tool, or build the image):" names semgrep
    And a line "Nothing to assess: dalfox" names dalfox
    And neither appears as a finding

  @id:editor-integrations.editor-diagnostics.011 @rule:nvim.scorecard.scan-first-when-nothing-scanned @inferred @source:extensions/nvim/lua/gandalf/commands.lua#ensure_scanned @questionable
  Scenario Outline: Asking for results before any scan has finished starts one first
    Given no scan has completed in this session
    When the developer runs <command>
    Then the notification reads "Gandalf: scanning…"
    And a workspace scan starts
    And <result> appears only if that scan produced a report

    Examples:
      | command        | result                |
      | :GandalfReport | the scorecard         |
      | :GandalfList   | the quickfix list     |
      | :GandalfFilter | the level picker      |
      | :GandalfHover on a dependency line | the dependency window |

  @id:editor-integrations.editor-diagnostics.012 @rule:nvim.hover.dependency-on-manifest-line @verified @source:extensions/nvim/lua/gandalf/core/packages.lua#M.package_at_cursor @test:extensions/nvim/tests/core_spec.lua#reads the manifest formats people actually have open @test:extensions/nvim/tests/core_spec.lua#names nothing on a line that is not a dependency
  Scenario Outline: The dependency named on a manifest line is recognised
    Given the cursor is on the line <line>
    When the developer runs :GandalfHover
    Then <result>

    Examples:
      | line                                           | result                                                        |
      | flask[async]==2.0                              | a window titled "flask" opens                                 |
      | "@types/node": "^20.0.0",                      | a window titled "@types/node" opens                           |
      | github.com/spf13/cobra v1.8.0                  | a window titled "github.com/spf13/cobra" opens                |
      | tokio = { version = "1", features = ["full"] } | a window titled "tokio" opens                                 |
      | dependencies = ["flask>=2.0"]                  | a window titled "flask" opens                                 |
      | gem 'rails', '~> 7.0'                          | a window titled "rails" opens                                 |
      | # a comment                                    | the notification reads "Gandalf: no dependency on this line." |
      | [tool.poetry]                                  | the notification reads "Gandalf: no dependency on this line." |

  @id:editor-integrations.editor-diagnostics.013 @rule:nvim.hover.dependency-findings @verified @source:extensions/nvim/lua/gandalf/ui.lua#M.hover_lines @test:extensions/nvim/tests/ui_spec.lua#shows the installed version next to the package when a gate reported one @test:extensions/nvim/tests/ui_spec.lua#carries the fix and the advisory link onto the finding it belongs to @test:extensions/nvim/tests/core_spec.lua#matches findings to a package regardless of case @test:extensions/nvim/tests/core_spec.lua#carries the package through normalization
  Scenario: Hovering a dependency shows what gandalf found against it, with the fix
    Given the last scan's trivy gate reported CVE-2024-29041 "Express.js open redirect" at HIGH against package Express, installed 4.17.1, fixed in 4.19.2
    When the developer hovers the line "express": "^4.18.0"
    Then the window heading reads "express  4.17.1"
    And it states "1 finding(s)"
    And the finding reads "● HIGH trivy · CVE-2024-29041" with its message indented below
    And it shows "fixed in: 4.19.2" and the advisory link

  @id:editor-integrations.editor-diagnostics.014 @rule:nvim.hover.no-findings-is-not-proof @verified @source:extensions/nvim/lua/gandalf/ui.lua#nothing_found_lines @test:extensions/nvim/tests/ui_spec.lua#says nothing was found, and how much of that is proof @test:extensions/nvim/tests/ui_spec.lua#does not hedge when every gate ran
  Scenario Outline: A dependency with no findings is called unproven when gates could not run
    Given the last scan found nothing against flask
    And <blocked gates>
    When the developer hovers the line flask==2.0.1
    Then the window reads "No findings against this dependency."
    And <warning>

    Examples:
      | blocked gates                      | warning                                                                                                                        |
      | the osv-scanner gate could not run | it adds "⚠ 1 gate(s) could not run, so this is not proof of anything:" naming osv-scanner and pointing to :checkhealth gandalf |
      | every gate ran                     | no warning is shown                                                                                                            |
