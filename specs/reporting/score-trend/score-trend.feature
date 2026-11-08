@domain:reporting @area:score-trend @from:gandalf/trend
Feature: Tracking the score over time
  Lets developers and CI operators see whether a repository's quality score is improving or regressing from one commit to the next, and gives editor integrations a shared history to chart.

  Background:
    Given a repository that gandalf scans
    And the score history is kept in ".gandalf-trend.jsonl" at the repository root

  @id:reporting.score-trend.001 @rule:reporting.score-trend.delta-vs-previous-commit @verified @source:src/gandalf/__main__.py#_meta_line @test:tests/test_trend.py#test_previous_score_skips_same_commit @test:tests/test_report.py#test_render_terminal_shows_delta @test:tests/test_report.py#test_render_html_shows_delta
  Scenario Outline: The scorecard shows the change in score since the previous commit
    Given the score history records commit "aaa111" with score <previous>
    And the working copy is at commit "bbb222"
    When the developer runs gandalf and the run scores <current>
    Then the scorecard verdict line reads "<current>/100 <delta>"
    And the HTML report verdict shows the same "<delta>"
    And the JSON report's score_delta is <number>

    Examples:
      | previous | current | delta         | number |
      | 80       | 90      | (+10 vs prev) | 10     |
      | 80       | 75      | (-5 vs prev)  | -5     |
      | 80       | 80      | (+0 vs prev)  | 0      |

  @id:reporting.score-trend.002 @rule:reporting.score-trend.rerun-not-compared-to-itself @verified @source:src/gandalf/trend.py#previous_score @test:tests/test_trend.py#test_previous_score_skips_same_commit
  Scenario: Re-scanning the same commit is compared with the commit before it, not with itself
    Given the score history records commit "aaa111" with score 80, then commit "bbb222" with score 90
    And the working copy is still at commit "bbb222"
    When the developer runs gandalf again and the run scores 95
    Then the scorecard verdict line reads "95/100 (+15 vs prev)"

  @id:reporting.score-trend.003 @rule:reporting.score-trend.no-delta-without-history @verified @source:src/gandalf/trend.py#previous_score @test:tests/test_trend.py#test_previous_score_none_without_file @test:tests/test_trend.py#test_previous_score_skips_same_commit
  Scenario Outline: Without an earlier commit in the history, no score change is shown
    Given the score history <history>
    And the working copy is at commit "aaa111"
    When the developer runs gandalf and the run scores 90
    Then the scorecard verdict line reads "90/100" with no "vs prev" note
    And the JSON report's score_delta is null

    Examples:
      | history                      |
      | does not exist yet           |
      | records only commit "aaa111" |

  @id:reporting.score-trend.004 @rule:reporting.score-trend.each-run-appended @verified @source:src/gandalf/trend.py#record @test:tests/test_trend.py#test_record_appends_jsonl @test:tests/test_run.py#test_reports_default_to_the_repo_and_record_a_trend
  Scenario: Every run adds its commit, score and time to the score history
    Given the score history already records commit "aaa111" with score 80
    When the developer runs gandalf at commit "bbb222" and the run scores 90
    Then the score history keeps the "aaa111" line unchanged
    And the score history gains one JSON line with commit "bbb222", score 90 and the run's generated_at time

  @id:reporting.score-trend.005 @rule:reporting.score-trend.no-trend-keeps-history-unchanged @verified @source:src/gandalf/__main__.py#_meta_line @test:tests/test_run.py#test_out_dir_and_no_trend_keep_the_worktree_clean
  Scenario: Opting out of the history still shows the score change but records nothing
    Given the score history records commit "aaa111" with score 80
    When the operator runs gandalf with "--no-trend" at commit "bbb222" and the run scores 90
    Then the scorecard verdict line reads "90/100 (+10 vs prev)"
    And the score history still holds only the "aaa111" line

  @id:reporting.score-trend.006 @rule:reporting.score-trend.unreadable-entries-ignored @inferred @source:src/gandalf/trend.py#previous_score @questionable
  Scenario: A damaged line in the score history is skipped instead of failing the run
    Given the score history records commit "aaa111" with score 80, followed by a half-written line
    When the developer runs gandalf at commit "bbb222" and the run scores 85
    Then the scorecard verdict line reads "85/100 (+5 vs prev)"
