@domain:editor-integrations @area:editor-diagnostics @from:extensions/nvim
Feature: Seeing findings in Neovim
  Puts gandalf's findings where a Neovim user works, as diagnostics on the lines they are about and in the quickfix list, ranked so the worst comes first.

  Background:
    Given the gandalf Neovim plugin is set up in a git project

  @id:editor-integrations.editor-diagnostics.001 @rule:nvim.findings.diagnostic-on-reported-line @verified @source:extensions/nvim/lua/gandalf/ui.lua#M.publish @test:extensions/nvim/tests/ui_spec.lua#places a finding on the line and column the gate named, zero-indexed @test:extensions/nvim/tests/ui_spec.lua#carries the gate and the category into the message, so a squiggle explains itself @test:extensions/nvim/tests/ui_spec.lua#keeps a finding with no place to put it out of the editor @test:extensions/nvim/tests/ui_spec.lua#replaces the whole namespace, so a rescan never leaves a stale squiggle
  Scenario: A finding becomes a diagnostic on the line and column the gate named
    Given the last scan reported a ruff finding E501 "line too long" at src/a.py line 2 column 3, category "Code quality"
    And src/a.py is open
    When the scan completes
    Then src/a.py shows a diagnostic on line 2, column 3 with source "gandalf" and code "E501"
    And its message reads "line too long" followed by "gate: ruff · category: Code quality · rule: E501"
    And findings with no file or line get no diagnostic
    And diagnostics from the previous scan are gone

  @id:editor-integrations.editor-diagnostics.002 @rule:nvim.findings.diagnostic-level-floor @verified @source:extensions/nvim/lua/gandalf/ui.lua#publishable @test:extensions/nvim/tests/ui_spec.lua#drops a finding below the configured floor @test:extensions/nvim/tests/ui_spec.lua#sorts an unrated finding by its gate outcome before applying the floor @test:extensions/nvim/tests/ui_spec.lua#publishes nothing at all when diagnostics are switched off
  Scenario Outline: Only findings at or above the configured level become diagnostics
    Given diagnostics are configured with <setting>
    And the last scan reported a <level> finding from a gate whose outcome was <outcome>
    When the findings are shown in the open file
    Then the finding <shown> as a diagnostic

    Examples:
      | setting               | level    | outcome | shown        |
      | min_level = high      | critical | warn    | is shown     |
      | min_level = high      | low      | warn    | is not shown |
      | min_level = high      | unrated  | fail    | is shown     |
      | min_level = high      | unrated  | pass    | is not shown |
      | severity.info = false | info     | warn    | is not shown |
      | enabled = false       | critical | fail    | is not shown |

  @id:editor-integrations.editor-diagnostics.003 @rule:nvim.findings.opened-file-gets-findings @inferred @source:extensions/nvim/lua/gandalf/init.lua#attach_autocmds
  Scenario: A file opened after a scan shows its findings
    Given a scan has completed with findings in src/a.py
    And src/a.py was not open during the scan
    When the developer opens src/a.py
    Then src/a.py shows the gandalf diagnostics from that scan

  @id:editor-integrations.editor-diagnostics.004 @rule:nvim.findings.failing-gate-always-listed @verified @source:extensions/nvim/lua/gandalf/core/findings.lua#M.normalize_gate @test:extensions/nvim/tests/core_spec.lua#never hides a red gate, whatever its summary says @test:extensions/nvim/tests/core_spec.lua#says nothing about a passing gate with no findings
  Scenario: A gate that did not pass but gave no findings still appears, with its summary
    Given the last scan's tests gate failed with summary "tests: 3 failure(s)" and no findings
    And the ruff gate passed with no findings
    When the developer runs :GandalfList
    Then the quickfix list has one entry, from the tests gate
    And its text reads "[tests] tests: 3 failure(s)"
    And nothing is listed for ruff

  @id:editor-integrations.editor-diagnostics.005 @rule:nvim.findings.worst-first @verified @source:extensions/nvim/lua/gandalf/core/levels.lua#M.compare_findings @test:extensions/nvim/tests/core_spec.lua#orders worst-first across levels
  Scenario: Findings are listed worst first
    Given the last scan reported a low finding, a critical finding, an unrated finding from a failing gate and a medium finding
    When the developer runs :GandalfList
    Then the quickfix list orders them critical, the failing gate's unrated finding, medium, low
    And findings of equal rank put a stated level before an unrated one, then order by gate, then file, then line

  @id:editor-integrations.editor-diagnostics.006 @rule:nvim.findings.quickfix-list @verified @source:extensions/nvim/lua/gandalf/commands.lua#M.list @test:extensions/nvim/tests/ui_spec.lua#marks critical and high as errors and everything else as warnings @test:extensions/nvim/tests/ui_spec.lua#flattens a multi-line message, which the list shows one row per entry
  Scenario: Every finding can be opened in the quickfix list
    Given the last scan reported a high finding at src/a.py:4:2 and a low finding at src/a.py:5:1
    When the developer runs :GandalfList
    Then the quickfix list titled "Gandalf" opens with both entries
    And the high finding is marked as an error and the low one as a warning
    And each entry reads "[gate] rule: message" on one line

  @id:editor-integrations.editor-diagnostics.007 @rule:nvim.findings.filter-by-level @inferred @source:extensions/nvim/lua/gandalf/commands.lua#M.filter
  Scenario: Findings can be narrowed to one severity level
    Given the last scan reported 2 high findings and 5 low findings
    When the developer runs :GandalfFilter and picks "High"
    Then the picker offers only High with count 2 and Low with count 5, worst first
    And the quickfix list titled "Gandalf: High" opens with the 2 high findings

  @id:editor-integrations.editor-diagnostics.008 @rule:nvim.findings.streamed-then-replaced @verified @source:extensions/nvim/lua/gandalf/state.lua#M.findings @test:extensions/nvim/tests/init_spec.lua#shows a streamed gate before the report lands @test:extensions/nvim/tests/init_spec.lua#replaces the streamed gate with what the report finally said @questionable
  Scenario: Findings appear gate by gate during a scan and the final report has the last word
    Given a previous scan has completed
    And gandalf supports --stream
    When a new scan streams the ruff gate before it finishes
    Then the finding list already shows ruff's newly streamed findings in place of its old ones
    And once the report is written, the list shows exactly what the report says for ruff
