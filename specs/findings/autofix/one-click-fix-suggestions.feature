@domain:findings @area:autofix @from:gandalf/suggest
Feature: Suggesting one-click fixes on pull request comments
  Lets a reviewer apply a scanner's own fix straight from the pull request page, while never offering a patch that could damage their code.

  Background:
    Givengandalf is posting review comments on a pull request
    Andthe changed file in the checkout is the version under review

  @id:findings.autofix.012 @rule:findings.suggestions.tool-fix-becomes-suggestion @verified @source:src/gandalf/suggest.py#for_anchor @test:tests/test_suggest.py#test_shellcheck_replacement @test:tests/test_suggest.py#test_shellcheck_zero_width_insertions @test:tests/test_suggest.py#test_semgrep_autofix @test:tests/test_suggest.py#test_codespell_correction_is_rebuilt_from_the_line @test:tests/test_suggest.py#test_normalised_fix_block @test:tests/test_pr_comments.py#test_comment_carries_the_tools_own_fix @test:tests/test_suggest.py#test_block_is_a_github_suggestion_fence
  Scenario Outline: A finding whose tool knows the fix carries it as an applicable suggestion
    Givena <tool> finding on line <line> of "<file>" whose line reads "<before>"
    Andthe tool reports the exact replacement for it
    Whengandalf comments on that line
    Thenthe comment ends with a GitHub suggestion block
    Andthe block's text is "<after>", the whole new text of the line

    Examples:
      | tool       | file | line | before           | after             |
      | ruff       | a.py | 12   | print( x )       | print(x )         |
      | shellcheck | s.sh | 1    | ls $foo          | ls "$foo"         |
      | semgrep    | a.py | 4    | x = 1  # colr me | x = 2  # colr me  |
      | codespell  | a.py | 4    | x = 1  # colr me | x = 1  # color me |
      | eslint     | a.js | 1    | const a = 1      | const a = 1;      |

  @id:findings.autofix.013 @rule:findings.suggestions.same-line-fixes-combined @verified @source:src/gandalf/suggest.py#for_anchor @test:tests/test_suggest.py#test_two_findings_on_one_line_make_one_suggestion
  Scenario: Several fixes on the same line are offered as one suggestion
    Giventwo findings on line 5 of "a.py", which reads "print( x )"
    Andone fix removes the space after the bracket and the other the space before it
    Whengandalf comments on line 5
    Thenthe comment carries a single suggestion reading "print(x)"

  @id:findings.autofix.014 @rule:findings.suggestions.untrustworthy-fix-left-as-prose @verified @source:src/gandalf/suggest.py#for_anchor @test:tests/test_suggest.py#test_a_finding_with_no_fix_suggests_nothing @test:tests/test_suggest.py#test_a_fix_that_changes_nothing_is_not_a_suggestion @test:tests/test_suggest.py#test_edits_off_the_end_of_the_file_are_refused @test:tests/test_suggest.py#test_conflicting_edits_are_refused @test:tests/test_suggest.py#test_codespell_ambiguous_correction_is_not_suggested @test:tests/test_suggest.py#test_oversized_suggestion_is_dropped @test:tests/test_suggest.py#test_a_fence_in_the_replacement_is_dropped @test:tests/test_pr_comments.py#test_findings_without_a_fix_are_unchanged
  Scenario Outline: A fix that cannot be applied safely is left out and the finding stays as prose
    Givena finding on line <line> of "a.py" where <situation>
    Whengandalf comments on that line
    Thenthe comment carries no suggestion block
    Andthe finding's description is still posted

    Examples:
      | line | situation                                     |
      | 4    | the tool reports no fix                       |
      | 1    | the fix would leave the line exactly as it is |
      | 99   | the fix points past the end of the file       |
      | 5    | two fixes overlap on the same characters      |
      | 4    | codespell offers several candidate spellings  |
      | 1    | the fixed text would span more than 40 lines  |
      | 1    | the fixed text contains a ``` fence           |

  @id:findings.autofix.015 @rule:findings.suggestions.starts-on-commented-line @verified @source:src/gandalf/suggest.py#for_anchor @test:tests/test_suggest.py#test_a_fix_below_the_comment_is_refused @questionable
  Scenario Outline: A suggestion is only offered when the fix starts on the line being commented on
    Givena finding whose fix rewrites line 4 of "a.py"
    Whengandalf comments on line <comment_line>
    Thenthe comment <outcome>

    Examples:
      | comment_line | outcome                           |
      | 4            | carries the suggestion for line 4 |
      | 3            | carries no suggestion block       |

  @id:findings.autofix.016 @rule:findings.suggestions.multi-line-within-diff @verified @source:src/gandalf/suggest.py#for_anchor @test:tests/test_suggest.py#test_multi_line_suggestion_must_stay_inside_the_diff @test:tests/test_pr_comments.py#test_multi_line_fix_makes_the_comment_span_the_range @test:tests/test_pr_comments.py#test_a_fix_reaching_outside_the_diff_is_left_as_prose
  Scenario Outline: A suggestion spanning several lines is offered only when every line is part of the change
    Givena finding on line 12 of "a.py" whose fix rewrites lines 12 to 13
    Andthe pull request adds lines <added>
    Whengandalf comments on line 12
    Thenthe comment <outcome>

    Examples:
      | added     | outcome                                                   |
      | 12 and 13 | covers lines 12 to 13 and carries the two-line suggestion |
      | 12 only   | covers line 12 only and carries no suggestion block       |

  @id:findings.autofix.017 @rule:findings.suggestions.line-deletion-stays-on-its-line @verified @source:src/gandalf/suggest.py#apply @test:tests/test_suggest.py#test_ruff_edits_become_the_new_line @test:tests/test_suggest.py#test_a_deleted_line_does_not_drag_in_the_line_below @test:tests/test_suggest.py#test_a_deletion_running_past_the_last_line_is_pulled_back
  Scenario Outline: A fix that deletes a line is suggested as an empty replacement of that line alone
    Givena finding whose fix deletes line <line> of a file with <total> lines
    Whengandalf comments on line <line>
    Thenthe comment carries an empty suggestion covering line <line> only

    Examples:
      | line | total |
      | 1    | 5     |
      | 2    | 2     |

  @id:findings.autofix.018 @rule:findings.suggestions.javascript-offsets-respect-emoji @verified @source:src/gandalf/suggest.py#utf16_edit @test:tests/test_suggest.py#test_utf16_offsets_survive_an_astral_character
  Scenario: A JavaScript fix lands in the right place even after an emoji earlier in the file
    Given"a.js" whose first line is a comment containing an emoji
    Andeslint reports a fix adding ";" at the end of line 2, "const a = 1"
    Whengandalf comments on line 2
    Thenthe suggestion reads "const a = 1;"
