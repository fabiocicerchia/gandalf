@domain:findings @area:finding-model @from:gandalf/locate
Feature: Locating findings that tools only describe in text
  Gives anyone reading the JSON report, the live stream or pull request comments a repo-relative file and line for findings whose tool wrote the location only into its message, without ever pointing at a file that is not there.

  Background:
    Given a repository checked out at a scan root
    And the file "src/d.py" exists in the repository

  @id:findings.finding-model.008 @rule:findings.locations.recovered-from-message-text @verified @source:src/gandalf/locate.py#place_from_prose @test:tests/test_findings.py#test_location_scraped_from_prose_and_trimmed @test:tests/test_pr_comments.py#test_message_only_location_still_anchors @test:tests/test_pr_comments.py#test_the_comment_does_not_repeat_the_location
  Scenario: A location written only in the message becomes the finding's file and line
    Given a gate reports a finding whose only text is "src/d.py:552: error: \"Gate\" has no attribute \"langs\"  [attr-defined]"
    When the operator runs gandalf
    Then the finding's path in the report is "src/d.py"
    And the finding's line in the report is 552
    And the finding's message starts with "error:" and no longer repeats "src/d.py:552"

  @id:findings.finding-model.009 @rule:findings.locations.only-existing-files-anchor @verified @source:src/gandalf/locate.py#_on_disk @test:tests/test_findings.py#test_prose_that_merely_looks_like_a_path_is_not_trusted
  Scenario: Text that only looks like a location does not anchor a finding
    Given the file "docs/missing.md" does not exist in the repository
    And a gate reports a finding "see docs/missing.md:12 for details"
    When the operator runs gandalf
    Then the finding's path in the report is empty
    And the finding's line in the report is 0
    And the finding's message is "see docs/missing.md:12 for details"

  @id:findings.finding-model.010 @rule:findings.locations.bare-path-in-sentence @verified @source:src/gandalf/locate.py#path_in_prose @test:tests/test_findings.py#test_sentence_in_a_location_key_becomes_the_message
  Scenario: A file named in a sentence anchors the finding and the sentence stays whole
    Given the file "src/e.py" exists in the repository
    And the format gate reports "Would reformat: src/e.py" with no line
    When the operator runs gandalf
    Then the finding's path in the report is "src/e.py"
    And the finding's line in the report is 0
    And the finding's message is "Would reformat: src/e.py"

  @id:findings.finding-model.012 @rule:findings.locations.reported-path-wins @inferred @source:src/gandalf/locate.py#place_from_prose
  Scenario: A file the tool reported is kept even when the message names another
    Given the file "src/a.py" exists in the repository
    And a gate reports a finding in "src/d.py" with no line and the text "src/a.py:7: duplicate of this block"
    When the operator runs gandalf
    Then the finding's path in the report is "src/d.py"
    And the finding's line in the report is 0
    And the finding's message is "src/a.py:7: duplicate of this block"
