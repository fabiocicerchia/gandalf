@domain:reporting @area:pull-request-comments @from:gandalf/pr-comments
Feature: Publishing the review to a GitHub pull request
  Lets a CI operator post gandalf's review to a pull request on every push without piling up duplicate comments or failing the build over a comment.

  Background:
    Given the operator runs gandalf with --pr 42 for repository example-org/example-app

  @id:reporting.pull-request-comments.007 @rule:reporting.pr-comments.sticky-summary @inferred @source:src/gandalf/pr_comments.py#_sticky_summary @questionable
  Scenario: Re-running edits the one summary comment instead of adding another
    Given an earlier run already posted a gandalf summary comment on pull request 42
    When the operator runs gandalf on pull request 42 again
    Then the existing summary comment is edited to the new verdict and timestamp
    And no second summary comment appears
    And the operator sees "PR #42: updated summary comment <id>; …"

  @id:reporting.pull-request-comments.008 @rule:reporting.pr-comments.inline-threads-reconciled @verified @source:src/gandalf/pr_comments.py#_sync_inline @test:tests/test_pr_comments.py#test_reconcile_resolves_obsolete_and_keeps_current
  Scenario: Re-running keeps unchanged comments, resolves fixed ones and re-posts findings that come back
    Given pull request 42 has an open gandalf thread on a.py line 12 that is still found
    And an open gandalf thread on a.py line 99 whose finding is now fixed
    And a resolved gandalf thread on a.py line 20 whose finding is found again
    When the operator runs gandalf on pull request 42 again
    Then the a.py line 12 thread is left untouched
    And the a.py line 99 thread is resolved, not deleted
    And a new comment is posted on a.py line 20

  @id:reporting.pull-request-comments.009 @rule:reporting.pr-comments.posting-needs-token-and-repo @verified @source:src/gandalf/pr_comments.py#post @test:tests/test_pr_comments.py#test_post_without_token_is_safe
  Scenario Outline: Without a token and a repository the review is written to a file but not posted
    Given GITHUB_TOKEN is <token>
    And the repository is <repo>
    When the operator runs gandalf with --pr 42
    Then the review is written to reports/<stem>-pr-comments.json
    And nothing is posted to the pull request
    And the operator sees "PR #42: no repo/token — skipped (wrote JSON instead)"

    Examples:
      | token | repo                                          |
      | unset | example-org/example-app from --pr-repo        |
      | set   | unset in both --pr-repo and GITHUB_REPOSITORY |

  @id:reporting.pull-request-comments.010 @rule:reporting.pr-comments.posting-failure-never-fails-run @verified @source:src/gandalf/pr_comments.py#post @test:tests/test_pr_comments.py#test_a_refusal_carries_githubs_own_reason @test:tests/test_pr_comments.py#test_a_graphql_error_raises_the_sentence_not_the_machinery
  Scenario Outline: A GitHub refusal is reported with GitHub's reason and does not fail the run
    Given GitHub <refusal>
    When the operator runs gandalf on pull request 42
    Then the gandalf run finishes with the same exit status it would have had without --pr
    And the operator sees "<message>"

    Examples:
      | refusal                                                                         | message                                                                             |
      | refuses the summary comment with 403 "Resource not accessible by integration"   | PR #42: post failed: HTTP 403: {"message":"Resource not accessible by integration"} |
      | forbids resolving 2 stale threads with "Resource not accessible by integration" | …, 0 resolved, 2 left open (Resource not accessible by integration)                 |
      | rejects 1 of 3 new inline comments                                              | posted 2 inline comment(s), 0 resolved, 1 rejected by GitHub                        |
