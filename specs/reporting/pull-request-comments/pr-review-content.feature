@domain:reporting @area:pull-request-comments @from:gandalf/pr-comments
Feature: Reviewing a pull request with gandalf findings
  Gives pull request reviewers each non-passing finding on the line the PR changed, with a one-click fix where the tool has one, plus a summary that leaves no finding out.

  Background:
    Given the operator runs gandalf with --pr-comments or --pr on a pull request

  @id:reporting.pull-request-comments.001 @rule:reporting.pr-comments.findings-anchor-to-added-lines @verified @source:src/gandalf/pr_comments.py#build @test:tests/test_pr_comments.py#test_diff_restricts_anchors_to_added_lines @test:tests/test_pr_comments.py#test_changed_set_excludes_off_diff_lines @test:tests/test_pr_comments.py#test_message_only_location_still_anchors @test:tests/test_pr_comments.py#test_container_paths_are_rebased_repo_relative @test:tests/test_pr_comments.py#test_the_comment_does_not_repeat_the_location
  Scenario Outline: A finding becomes an inline comment only on a line the pull request adds
    Given a non-passing gate reports a finding at <location>
    And the pull request <diff_state>
    When the operator generates the pull request review
    Then the finding appears <where>

    Examples:
      | location                                                   | diff_state                             | where                                                            |
      | a.py:12                                                    | adds line 12 of a.py                   | as an inline comment on a.py line 12, right-hand side            |
      | b.py:3                                                     | does not add any line of b.py          | in the summary's other-findings list as "b.py:3"                 |
      | a.py:12                                                    | has no line diff and changes a.py      | as an inline comment on a.py line 12                             |
      | b.py:3                                                     | has no line diff and changes only a.py | in the summary's other-findings list                             |
      | a message "a.py:8: error: bad" with no structured location | has no line diff and changes a.py      | as an inline comment on a.py line 8                              |
      | /src/a.py:12 inside the tools container                    | adds line 12 of a.py                   | as an inline comment on a.py line 12, with no "/src" in its text |

  @id:reporting.pull-request-comments.002 @rule:reporting.pr-comments.same-line-findings-merge @verified @source:src/gandalf/pr_comments.py#build @test:tests/test_pr_comments.py#test_same_line_findings_merge
  Scenario: Findings on the same line share one inline comment
    Given the ruff gate fails with E501 and E502 both on a.py line 12
    And the pull request changes a.py
    When the operator generates the pull request review
    Then there is exactly one inline comment on a.py line 12
    And its text names both E501 and E502, each tagged with the gate name `ruff`

  @id:reporting.pull-request-comments.003 @rule:reporting.pr-comments.unanchored-findings-kept-in-summary @verified @source:src/gandalf/pr_comments.py#review_payload @test:tests/test_pr_comments.py#test_overflow_is_collapsed @test:tests/test_pr_comments.py#test_passing_gate_contributes_nothing
  Scenario: Findings that cannot sit on a changed line are listed in the summary, never dropped
    Given 40 findings from failing gates fall outside the lines the pull request adds
    When the operator generates the pull request review
    Then the summary holds a collapsed section headed "Other findings — 40 not on changed lines"
    And it lists the first 30 findings, each with its traffic-light icon, gate name, location and message
    And the list ends with "…and 10 more"

  @id:reporting.pull-request-comments.004 @rule:reporting.pr-comments.summary-shows-verdict @verified @source:src/gandalf/pr_comments.py#review_payload @test:tests/test_pr_comments.py#test_review_payload_shape @test:tests/test_pr_comments.py#test_body_carries_marker_and_update_stamp @test:tests/test_pr_comments.py#test_brand_defaults_and_override
  Scenario Outline: The review summary shows the verdict and score and never requests changes
    Given the run's verdict is <verdict> with a score of <score>/100
    And <findings>
    When the operator generates the pull request review
    Then the summary heading reads "## 🧙 gandalf — <word> · <score>/100"
    And the summary says "<note>"
    And the summary ends with a "Last updated" UTC timestamp
    And the review is a plain comment, not a request for changes

    Examples:
      | verdict | score | word  | findings                         | note                       |
      | red     | 67    | RED   | 3 findings land on changed lines | 3 inline comment(s) below. |
      | green   | 100   | GREEN | every gate passes                | No findings. ✅             |

  @id:reporting.pull-request-comments.005 @rule:reporting.pr-comments.one-click-fix-suggestions @verified @source:src/gandalf/pr_comments.py#_comment @test:tests/test_pr_comments.py#test_comment_carries_the_tools_own_fix @test:tests/test_pr_comments.py#test_multi_line_fix_makes_the_comment_span_the_range @test:tests/test_pr_comments.py#test_a_fix_reaching_outside_the_diff_is_left_as_prose @test:tests/test_pr_comments.py#test_summary_counts_the_applicable_fixes
  Scenario Outline: A finding its tool can fix carries a one-click suggested change
    Given the ruff gate fails with a fix that rewrites <fix_lines> of a.py
    And the pull request adds lines 12 and 13 of a.py
    When the operator generates the pull request review
    Then the inline comment covers <comment_lines>
    And the comment <suggestion>
    And the summary <summary_note>

    Examples:
      | fix_lines      | comment_lines  | suggestion                                                 | summary_note                                                     |
      | line 12        | line 12        | ends with a suggested-change block holding the fixed line  | says "1 carries a suggested fix" and points to Commit suggestion |
      | lines 12 to 13 | lines 12 to 13 | ends with a suggested-change block holding the replacement | says "1 carries a suggested fix"                                 |
      | lines 13 to 14 | line 13 only   | holds the finding text with no suggested change            | does not mention a suggested fix                                 |

  @id:reporting.pull-request-comments.006 @rule:reporting.pr-comments.rebrandable-name @verified @source:src/gandalf/pr_comments.py#_brand @test:tests/test_pr_comments.py#test_brand_defaults_and_override
  Scenario: The review can be rebranded without changing gandalf
    Given the operator sets GANDALF_PR_TITLE to "acme-bot" and GANDALF_PR_ICON to "🚀"
    When the operator generates the pull request review
    Then the summary heading starts with "## 🚀 acme-bot — "
    And each inline comment is headed "**acme-bot**"
    And the summary heading no longer says "gandalf"
