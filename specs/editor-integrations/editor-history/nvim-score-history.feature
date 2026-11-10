@domain:editor-integrations @area:editor-history @from:extensions/nvim
Feature: Browsing score history in Neovim
  Lets a Neovim user see whether quality is improving commit by commit, and score a commit that has never been measured.

  Background:
    Given the gandalf Neovim plugin is set up in a git project

  @id:editor-integrations.editor-history.001 @rule:nvim.history.commits-with-scores @verified @source:extensions/nvim/lua/gandalf/commands.lua#M.history @test:extensions/nvim/tests/init_spec.lua#offers the commits git log reported, newest first @test:extensions/nvim/tests/init_spec.lua#says nothing has been scanned when the trend log is empty @test:extensions/nvim/tests/core_spec.lua#reports the delta, and says so when there is none @test:extensions/nvim/tests/core_spec.lua#scales the sparkline across the observed range, not 0-100
  Scenario: The history lists recent commits with their scores and the change from the previous score
    Given the project's last commits, newest first, are c3 "fix: login", b2 "feat: export" and a1 "chore: init"
    And the trend log scores a1 at 80 and c3 at 85, and has no score for b2
    When the developer runs :GandalfHistory
    Then the picker lists up to the 40 most recent commits, newest first
    And c3 reads "85/100 +5", b2 reads "— not scanned" and a1 reads "80/100"
    And the prompt reads "Score history — <sparkline> over 2 of 3 commit(s)"

  @id:editor-integrations.editor-history.002 @rule:nvim.history.latest-score-per-commit @verified @source:extensions/nvim/lua/gandalf/core/trend.lua#M.parse_trend @test:extensions/nvim/tests/core_spec.lua#takes the last line for a commit, because the log is append-only @test:extensions/nvim/tests/core_spec.lua#ignores a truncated final line
  Scenario: A rescanned commit shows its newest score
    Given the trend log scores abc1234 at 70 and later again at 75
    When the developer runs :GandalfHistory
    Then abc1234 reads "75/100"

  @id:editor-integrations.editor-history.003 @rule:nvim.history.score-selected-commit @verified @source:extensions/nvim/lua/gandalf/commands.lua#scan_commit @test:extensions/nvim/tests/core_spec.lua#lets a named commit into the trend log, because that is what it is for
  Scenario: Picking a commit from the history scores it and opens its scorecard
    Given commit b2 has no score in the trend log
    When the developer picks b2 in :GandalfHistory
    Then the notification reads "Gandalf: scanning b2…"
    And gandalf is run with "--commit b2" and without "--no-trend", so the score is recorded
    And the scorecard opens when the scan produces a report
