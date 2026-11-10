@domain:editor-integrations @area:auto-scan @from:extensions/nvim
Feature: Scanning automatically from Neovim
  Keeps a Neovim user's findings current without them asking, while never running gandalf on a keystroke or because of its own output.

  Background:
    Given the gandalf Neovim plugin is set up in a git project

  @id:editor-integrations.auto-scan.001 @rule:nvim.autoscan.trigger-modes @inferred @source:extensions/nvim/lua/gandalf/init.lua#M.setup
  Scenario Outline: The scan trigger decides when gandalf runs by itself
    Given scan.trigger is <trigger>
    And scan.on_startup is true
    When the developer works in the project
    Then saving a file <save>
    And a workspace sweep <sweep>
    And a workspace scan 5 seconds after setup <startup>

    Examples:
      | trigger              | save                       | sweep                       | startup      |
      | on_save              | starts a scan of that file | never runs                  | runs         |
      | on_save_and_interval | starts a scan of that file | runs every interval_minutes | runs         |
      | interval             | starts nothing             | runs every interval_minutes | runs         |
      | manual               | starts nothing             | never runs                  | does not run |

  @id:editor-integrations.auto-scan.002 @rule:nvim.autoscan.saves-debounced @inferred @source:extensions/nvim/lua/gandalf/init.lua#schedule_scan @questionable
  Scenario: A burst of saves becomes one scan after a quiet period
    Given scan.trigger is on_save with debounce_ms 1500
    When the developer saves src/a.py and then src/b.py within 1.5 seconds
    Then one file scan starts 1.5 seconds after the last save
    And it scans src/b.py only
    And the log records "scan (saved src/b.py)"

  @id:editor-integrations.auto-scan.003 @rule:nvim.autoscan.own-output-ignored @inferred @source:extensions/nvim/lua/gandalf/init.lua#scannable @questionable
  Scenario Outline: Saving gandalf's own output never triggers a scan
    Given scan.trigger is on_save
    When the developer saves <path>
    Then no scan is started

    Examples:
      | path                        | note                            |
      | .git/COMMIT_EDITMSG         | inside .git                     |
      | reports/gandalf-report.json | inside reports/                 |
      | .gandalf-trend.jsonl        | file name starts with .gandalf- |
      | /tmp/notes.txt              | outside the project             |
