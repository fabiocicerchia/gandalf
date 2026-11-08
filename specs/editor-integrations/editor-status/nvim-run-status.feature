@domain:editor-integrations @area:editor-status @from:extensions/nvim
Feature: Following a scan's progress and cost in Neovim
  Shows a Neovim user what a run is doing, how it ended and where its time went, so slow or broken scans can be diagnosed.

  Background:
    Given the gandalf Neovim plugin is set up in a git project

  @id:editor-integrations.editor-status.001 @rule:nvim.status.statusline @verified @source:extensions/nvim/lua/gandalf/state.lua#M.statusline @test:extensions/nvim/tests/init_spec.lua#reads the verdict and the score into the status line @test:extensions/nvim/tests/core_spec.lua#describes itself for a status line @test:extensions/nvim/tests/init_spec.lua#stops calling itself busy once the run is over
  Scenario Outline: The status line shows progress during a run and the verdict after it
    Given <state>
    When the status line is drawn
    Then the gandalf component reads <text>

    Examples:
      | state                                                                         | text                            |
      | the plugin has not been set up                                                | "" (empty)                      |
      | a scan is running and gandalf reported 12 of 37 gates done, currently semgrep | "gandalf gates 12/37 · semgrep" |
      | a scan is running and gandalf reported the stage "Resolving scope"            | "gandalf Resolving scope"       |
      | a scan is running with no progress reported yet                               | "gandalf scanning"              |
      | the last scan scored 88/100 with a green verdict                              | "gandalf GREEN 88/100"          |
      | no scan has completed                                                         | "" (empty)                      |

  @id:editor-integrations.editor-status.002 @rule:nvim.status.gate-timings-skip-list @inferred @source:extensions/nvim/lua/gandalf/commands.lua#M.timings
  Scenario: Gate timings are listed slowest first and a pick copies a skip list
    Given the last scan recorded semgrep taking 42.0s and ruff taking 1.2s
    When the developer runs :GandalfTimings and picks semgrep
    Then the picker lists semgrep before ruff with their durations and summaries
    And the clipboard holds "[gandalf]" and "skip = [\"semgrep\"]"
    And the notification tells them to paste it into a .gandalf.toml and point config_path at it

  @id:editor-integrations.editor-status.003 @rule:nvim.status.scan-log @verified @source:extensions/nvim/lua/gandalf/commands.lua#M.show_log @test:extensions/nvim/tests/init_spec.lua#logs the command it ran and the verdict it got
  Scenario: The log shows each command run and how it ended
    Given a workspace scan finished with a green verdict, 88/100 and 1 finding
    When the developer runs :GandalfLog
    Then a window titled "Gandalf log" opens
    And it has a timestamped line "scan (command): <the full gandalf command line>"
    And it has a line "done: pass 88/100, 1 finding(s)"
    And with nothing logged it reads "nothing logged yet"

  @id:editor-integrations.editor-status.004 @rule:nvim.status.debug-trace-in-log @inferred @source:extensions/nvim/lua/gandalf/scan.lua#on_stderr
  Scenario: With debug on, gandalf's own timing trace streams into the log during the run
    Given the plugin is configured with scan.debug = true
    When a scan runs
    Then gandalf is run with GANDALF_DEBUG=1
    And each trace line gandalf writes appears in :GandalfLog while the scan is still running
