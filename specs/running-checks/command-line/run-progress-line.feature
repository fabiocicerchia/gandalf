@domain:running-checks @area:command-line @from:gandalf/progress
Feature: Watching a run's progress
  Shows the operator, and editors that launch gandalf, which stage a run is in and how many gates have finished, without cluttering piped output or the scorecard.

  Background:
    Given a repository with gates that apply to it

  @id:running-checks.command-line.012 @rule:cli.progress.shown-only-on-terminal-or-when-forced @verified @source:src/gandalf/progress.py#Progress @test:tests/test_debug.py#test_progress_keeps_drawing_under_debug
  Scenario Outline: The progress line appears on a terminal or when forced, and stays silent in piped output
    Given stderr <stderr_kind>
    And GANDALF_PROGRESS is <env>
    When the operator runs gandalf
    Then the progress line on stderr is <shown>

    Examples:
      | stderr_kind        | env   | shown              |
      | is a terminal      | unset | shown              |
      | is piped to a file | unset | not written at all |
      | is piped to a file | 1     | shown              |
      | is piped to a file | 0     | not written at all |

  @id:running-checks.command-line.013 @rule:cli.progress.stages-counted-per-run-mode @inferred @source:src/gandalf/__main__.py#_progress
  Scenario Outline: The progress line counts only the stages this run will go through
    Given the run <llm> the LLM summary
    And the run <fix> fixes
    When the operator runs gandalf
    Then the progress line steps through <stages>
    And each step reads "[n/<total>]" followed by its stage label, n counting up from 1

    Examples:
      | llm              | fix             | stages                                                                          | total |
      | skips (--no-llm) | does not apply  | Resolving scope, Running N gates, Writing reports                               | 3     |
      | includes         | does not apply  | Resolving scope, Running N gates, LLM analysis, Writing reports                 | 4     |
      | includes         | applies (--fix) | Resolving scope, Applying fixes, Running N gates, LLM analysis, Writing reports | 5     |
      | skips (--no-llm) | applies (--fix) | Resolving scope, Applying fixes, Running N gates, Writing reports               | 4     |

  @id:running-checks.command-line.014 @rule:cli.progress.coexists-with-debug-log @verified @source:src/gandalf/progress.py#Progress @test:tests/test_debug.py#test_progress_keeps_drawing_under_debug @test:tests/test_debug.py#test_hooks_bracket_a_log_line
  Scenario: Under debug logging, each debug line prints whole and the progress line comes back beneath it
    Given the progress line is shown
    And debug logging is on
    When a debug line is written while gates run
    Then the progress line is cleared
    And the debug line is written on its own line
    And the progress line is drawn again beneath it, starting with a carriage return
