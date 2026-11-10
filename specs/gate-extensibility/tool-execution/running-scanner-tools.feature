@domain:gate-extensibility @area:tool-execution @from:gandalf/toolrun
Feature: Running scanner tools on the host or in the tools image
  Lets operators run gate scanners from their own PATH or the prebuilt gandalf-tools image without ever having a tool that did not really run show up as a clean pass.

  Background:
    Given a repository the operator scans with gandalf

  @id:gate-extensibility.tool-execution.001 @rule:tools.resolution.host-then-image-then-not-run @verified @source:src/gandalf/toolrun.py#_dockerize @test:tests/test_tool_provenance.py#test_host_resolution_is_recorded @test:tests/test_tool_provenance.py#test_image_resolution_is_recorded @test:tests/test_tool_provenance.py#test_an_unresolvable_tool_is_not_claimed_to_have_run
  Scenario Outline: A scanner runs from the host PATH first, then from the tools image, otherwise not at all
    Given <tool> is <on_path> on the host PATH
    And the gandalf-tools image is <image_state>
    When the operator runs a scan that uses <tool>
    Then <tool> runs <where>
    And the report records <tool> as <source>

    Examples:
      | tool  | on_path | image_state   | where                                                                  | source     |
      | ruff  | present | built locally | directly on the host                                                   | host       |
      | trivy | absent  | built locally | in a throwaway gandalf-tools container mounting the repository at /src | image      |
      | trivy | absent  | not built     | nowhere; its gate is reported as unavailable and skipped               | not listed |
      | go    | absent  | built locally | nowhere; language toolchains are host-only                             | not listed |

  @id:gate-extensibility.tool-execution.002 @rule:tools.image.never-pulled @inferred @source:src/gandalf/toolrun.py#tools_image_available
  Scenario: Gandalf never downloads the tools image on its own
    Given the gandalf-tools image has not been built on this machine
    And trivy is not on the host PATH
    When the operator runs a scan that uses trivy
    Then no image is pulled from a registry
    And the trivy gate reports "trivy unavailable (no host binary or gandalf-tools image) — skipped"

  @id:gate-extensibility.tool-execution.003 @rule:tools.failure.never-a-clean-pass @verified @source:src/gandalf/toolrun.py#run_tool @test:tests/test_run.py#test_a_container_that_never_started_is_not_a_clean_scan
  Scenario Outline: A scanner that did not actually run is never reported as a clean pass
    Given trivy resolves to the gandalf-tools image
    And <failure>
    When the operator runs a scan that uses trivy
    Then the trivy gate reports "trivy: did not run (timeout or tool unavailable) — skipped"
    And the trivy gate is not counted as passing

    Examples:
      | failure                                               |
      | docker refuses to start the container (exit code 125) |
      | the image does not contain the trivy executable       |
      | the image cannot be found by docker                   |
      | trivy runs longer than its timeout                    |

  @id:gate-extensibility.tool-execution.004 @rule:tools.timeout.stops-the-tool @verified @source:src/gandalf/toolrun.py#_reap @test:tests/test_gandalf.py#test_reap_kills_the_container_not_just_the_docker_client @test:tests/test_gandalf.py#test_communicate_kills_the_child_on_timeout
  Scenario: A scanner that times out or is cancelled is stopped, including its container
    Given semgrep runs in a gandalf-tools container
    And semgrep is still running when its timeout expires
    When the operator's scan reaches the semgrep timeout
    Then the semgrep container is killed
    And no semgrep process is left running after the scan
    And the semgrep gate reports that it did not run

  @id:gate-extensibility.tool-execution.005 @rule:tools.timeout.per-gate-budget @inferred @source:src/gandalf/toolrun.py#run_tool @questionable
  Scenario Outline: Each scanner call is bounded by its gate's timeout, defaulting to 120 seconds
    Given <setting>
    When the operator runs a scan with a scanner that never finishes
    Then the scanner is stopped after <seconds> seconds
    And its gate reports that it did not run

    Examples:
      | setting                                 | seconds |
      | no timeout is configured                | 120     |
      | GANDALF_GATE_TIMEOUT is 300             | 300     |
      | the gate has a configured timeout of 45 | 45      |

  @id:gate-extensibility.tool-execution.006 @rule:running.deadline.unstarted-tools-did-not-run @verified @source:src/gandalf/toolrun.py#run_tool @test:tests/test_run.py#test_past_the_deadline_a_tool_is_not_started @test:tests/test_run.py#test_without_a_deadline_a_tool_runs_normally
  Scenario: Past the run deadline no further scanner is started, and the run still ends with a scorecard
    Given the operator set a run deadline with --deadline
    And the deadline has passed while gates are still queued
    When the operator's scan reaches a gate that needs a scanner
    Then the scanner is not started
    And that gate is marked did not run
    And gates that finished keep their results in the report
