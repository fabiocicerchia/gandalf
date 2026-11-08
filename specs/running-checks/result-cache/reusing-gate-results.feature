@domain:running-checks @area:result-cache @from:gandalf/cache
Feature: Reusing gate results between runs
  Lets an operator re-run gandalf with --cache and skip gates whose scanned files have not changed, without ever being served an answer that is stale for a reason the files cannot show.

  Background:
    Given Given a repository with tracked source files
    And And the operator runs gandalf with "--cache", which keeps results in ".gandalf-cache.json" at the repository root unless another path is given

  @id:running-checks.result-cache.001 @rule:checks.result-cache.reuse-when-files-unchanged @verified @source:src/gandalf/cache.py#Plan @test:tests/test_cache.py#test_get_put_roundtrip @test:tests/test_cache.py#test_load_save_roundtrip
  Scenario: A gate is not re-run when the files it scans are unchanged
    Given a previous cached run in which the "ruff" gate reported "ruff: 1 issue" with a WARN outcome
    And no scanned file has changed since that run
    When the operator runs gandalf again with "--cache"
    Then the "ruff" gate is not executed again
    And the report shows "ruff" with outcome WARN, score 0.8 and summary "ruff: 1 issue"
    And the reused result is also emitted on the live result stream when "--stream" is on
    And gates are listed in the report in gate order, whether their result was reused or fresh

  @id:running-checks.result-cache.002 @rule:checks.result-cache.invalidated-by-scope-or-toolchain-change @verified @source:src/gandalf/cache.py#content_hash @test:tests/test_cache.py#test_content_hash_changes_with_file_content @test:tests/test_cache.py#test_salt_changes_the_key @test:tests/test_cache.py#test_toolchain_salt_tracks_the_image_id @questionable
  Scenario Outline: A change to the scanned files or to gandalf's toolchain makes gates run again
    Given a previous cached run in which every gate produced a result
    And <change> since that run
    When the operator runs gandalf again with "--cache"
    Then the gates are <outcome>

    Examples:
      | change                                                           | outcome                      |
      | the contents of a scanned file changed                           | run again                    |
      | a scanned file was renamed with identical contents               | run again                    |
      | the scanner-tools image was rebuilt under the same tag           | run again                    |
      | gandalf was upgraded to a new version                            | run again                    |
      | only a file excluded through .gandalfignore or --exclude changed | reused from the previous run |
      | only a scanner installed on the host PATH was upgraded           | reused from the previous run |

  @id:running-checks.result-cache.003 @rule:checks.result-cache.advisory-results-expire @verified @source:src/gandalf/cache.py#max_age @test:tests/test_cache.py#test_advisory_gates_expire_but_others_do_not @test:tests/test_cache.py#test_a_stale_advisory_entry_is_a_miss @test:tests/test_cache.py#test_entry_without_a_timestamp_is_expired_when_a_max_age_applies @test:tests/test_cache.py#test_a_gate_may_override_its_own_ttl
  Scenario Outline: Vulnerability and licence verdicts are reused for at most six hours
    Given a previous cached run in which the "<gate>" gate reported no known vulnerabilities
    And no scanned file has changed since that run
    And that run was <age> ago
    When the operator runs gandalf again with "--cache"
    Then the "<gate>" gate is <outcome>

    Examples:
      | gate        | age     | outcome                      |
      | trivy       | 2 hours | reused from the previous run |
      | trivy       | 7 hours | run again                    |
      | osv_scanner | 7 hours | run again                    |
      | ruff        | 7 days  | reused from the previous run |

  @id:running-checks.result-cache.004 @rule:checks.result-cache.off-for-inputs-outside-files @inferred @source:src/gandalf/__main__.py#_cache_plan
  Scenario Outline: Results are never reused when the run is given a target, title or body
    Given a previous cached run in which every gate produced a result
    And no scanned file has changed since that run
    When the operator runs gandalf again with "--cache" and "<option>"
    Then every applicable gate runs again
    And the result file is neither read nor updated by this run

    Examples:
      | option                               |
      | --target https://staging.example.com |
      | --title "Add login rate limit"       |
      | --body "Closes #42"                  |

  @id:running-checks.result-cache.005 @rule:checks.result-cache.unusable-file-means-full-run @verified @source:src/gandalf/cache.py#load @test:tests/test_cache.py#test_load_missing_file_is_empty
  Scenario Outline: A missing or damaged result file leads to a full run, not an error
    Given the result file is <state>
    When the operator runs gandalf with "--cache"
    Then every applicable gate runs
    And the run completes with no error about the result file
    And the result file afterwards holds this run's results

    Examples:
      | state                                                          |
      | absent                                                         |
      | not valid JSON                                                 |
      | written by an older gandalf whose result shape no longer loads |
