@domain:running-checks @area:debug-logging @from:gandalf/debug
Feature: Tracing a run with debug logging
  Lets an operator see where a gandalf run spends its time and which external commands it ran, without polluting the scorecard or JSON report that other tools consume.

  Background:
    Given a repository with gates to evaluate

  @id:running-checks.debug-logging.001 @rule:running-checks.debug-logging.off-by-default @verified @source:src/gandalf/debug.py#log @test:tests/test_debug.py#test_silent_when_disabled @test:tests/test_debug.py#test_hooks_do_not_fire_when_debug_is_off
  Scenario: A run prints no debug trace unless asked to
    Given the operator has not passed --debug
    And GANDALF_DEBUG is not set to 1
    When the operator runs gandalf
    Then no line stamped "[gandalf +" appears on stderr
    And no external command lines are traced

  @id:running-checks.debug-logging.002 @rule:running-checks.debug-logging.opt-in-switches @verified @source:src/gandalf/debug.py#enable @test:tests/test_debug.py#test_writes_when_enabled @questionable
  Scenario Outline: Debug tracing is turned on by the --debug flag or GANDALF_DEBUG=1
    Given the operator has <switch>
    When the operator runs gandalf
    Then debug trace lines are <outcome> on stderr

    Examples:
      | switch                 | outcome     |
      | passed --debug         | written     |
      | set GANDALF_DEBUG=1    | written     |
      | set GANDALF_DEBUG=true | not written |
      | set GANDALF_DEBUG=0    | not written |

  @id:running-checks.debug-logging.003 @rule:running-checks.debug-logging.stderr-only-elapsed-stamped @verified @source:src/gandalf/debug.py#log @test:tests/test_debug.py#test_writes_when_enabled @questionable
  Scenario: Debug lines go to stderr with an elapsed-time stamp and never touch stdout
    Given the operator has passed --debug
    And the operator asked for the JSON report on stdout
    When the operator runs gandalf
    Then each debug line on stderr starts with "[gandalf +" followed by the elapsed seconds, e.g. "[gandalf +  1.42s] config: (defaults)"
    And stdout contains only the JSON report and still parses

  @id:running-checks.debug-logging.004 @rule:running-checks.debug-logging.traces-gates-and-commands @inferred @source:src/gandalf/toolrun.py#run_tool
  Scenario: The debug trace shows each gate's start, outcome and duration and every external command
    Given the operator has passed --debug
    And the ruff gate runs an external command
    When the operator runs gandalf
    Then stderr shows "gate ruff: start" when the gate begins running
    And stderr shows "gate ruff: <outcome> in <seconds>s" when it finishes
    And stderr shows "run (timeout=<n>s): <command line>" before the command and "done rc=<code> in <seconds>s: <tool>" after it
    And stderr shows each run stage as "stage <i>/<total>: <label>"

  @id:running-checks.debug-logging.005 @rule:running-checks.debug-logging.coexists-with-progress-bar @verified @source:src/gandalf/debug.py#around_log @test:tests/test_debug.py#test_hooks_bracket_a_log_line @test:tests/test_debug.py#test_progress_keeps_drawing_under_debug
  Scenario: Debug lines and the progress bar are both shown during a run
    Given the operator has passed --debug
    And stderr is a terminal so the progress bar is shown
    When the operator runs gandalf
    Then each debug line appears on a line of its own
    And the progress bar is redrawn below the debug line
    And after the run finishes no progress bar is drawn over the scorecard
