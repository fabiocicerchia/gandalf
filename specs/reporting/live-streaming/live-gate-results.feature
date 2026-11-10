@domain:reporting @area:live-streaming @from:gandalf/stream
Feature: Streaming gate results while a check runs
  Lets editors and other consumers show each gate's result as soon as it finishes, instead of waiting for the final report.

  Background:
    Given the operator runs gandalf with --stream

  @id:reporting.live-streaming.001 @rule:reporting.live-streaming.one-line-per-gate @verified @source:src/gandalf/stream.py#GateStream @test:tests/test_run.py#test_stream_emits_one_ndjson_line_per_gate
  Scenario: A streamed run announces its scope and gate count, then reports every gate as it finishes
    Given a repository where 1 gate applies to the working tree
    When the operator runs the check on the working tree
    Then the first JSON line on standard output is {"event": "start", "scope": "working-tree", "gates": 1}
    And exactly one {"event": "gate"} line follows for each gate, in the order the gates finish
    And each gate line carries its index and the total, e.g. index 1 of 1
    And each gate line carries the gate's name, outcome, findings, category, duration in seconds and whether it is blocking

  @id:reporting.live-streaming.002 @rule:reporting.live-streaming.cache-hits-reported @verified @source:src/gandalf/__main__.py#main @test:tests/test_run.py#test_stream_reports_cache_hits_too
  Scenario: Gates answered from the result cache are still streamed
    Given the result cache is enabled
    And a previous run cached every gate's result and no scanned file has changed
    When the operator runs the check again
    Then standard output carries a start line followed by one gate line per cached gate
    And the cached gate's line names the gate, e.g. "build"

  @id:reporting.live-streaming.003 @rule:reporting.live-streaming.no-verdict-in-feed @inferred @source:src/gandalf/stream.py#GateStream
  Scenario: The live feed gives no overall verdict and its scores are preliminary
    Given severity weighting is enabled for the project
    When the operator runs the check
    Then no streamed line carries an overall verdict or composite score
    And each gate line's score is not severity-weighted
    And the final report's score for the same gate may differ from the streamed one

  @id:reporting.live-streaming.004 @rule:reporting.live-streaming.baseline-written-same-run @inferred @source:src/gandalf/__main__.py#_stream @questionable
  Scenario: Findings accepted during the same run still appear in that run's live feed
    Given a gate reports a finding that is not yet in the baseline
    When the operator runs the check with --stream and --write-baseline
    Then the gate's streamed line lists the finding
    And the final report for the same run shows the finding as suppressed
