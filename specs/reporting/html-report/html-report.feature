@domain:reporting @area:html-report @from:gandalf/render-html
Feature: Reading the HTML scorecard
  Gives developers, reviewers and CI consumers a single shareable HTML page with the verdict, per-category scores, every gate's status and the AI write-up, readable offline and safe to open.

  Background:
    Given Given gandalf has finished evaluating a repository
    And And the operator asked for the HTML report

  @id:reporting.html-report.005 @rule:reporting.html-report.self-contained-file @verified @source:src/gandalf/render_html.py#render_html @test:tests/test_report.py#test_render_html_smoke
  Scenario: The HTML report opens on its own without fetching anything
    Given The run produced gate results
    When the operator opens the HTML report from a CI artifact, an email attachment or a file:// URL
    Then the page is one complete HTML document from <!DOCTYPE html> to </html>
    And its stylesheet and script are embedded in the page
    And no stylesheet, script or font is loaded from elsewhere

  @id:reporting.html-report.006 @rule:reporting.html-report.untrusted-text-escaped @inferred @source:src/gandalf/render_html.py#_md_inline
  Scenario: Text from findings, diffs and the AI write-up cannot inject markup into the report
    Given A gate finding message contains "<script>alert(1)</script>"
    And And the AI summary contains a link to "javascript:alert(1)" and a link to "https://example.com/docs"
    When the operator opens the HTML report
    Then the finding is shown as the literal text "<script>alert(1)</script>"
    And the https://example.com/docs link is clickable
    And the javascript: link is shown as plain text, not as a link

  @id:reporting.html-report.007 @rule:reporting.html-report.verdict-header @verified @source:src/gandalf/render_html.py#render_html @test:tests/test_report.py#test_render_html_shows_delta @test:tests/test_report.py#test_render_html_smoke
  Scenario Outline: The report header shows the verdict, the score, its change and the commit
    Given The overall verdict is <verdict> with score <score>
    And And the score changed by <delta> since the previous run
    And And the run evaluated commit "abc123" with subject "fix"
    When the operator opens the HTML report
    Then the verdict banner reads "<verdict> · <score>/100<shown_delta>"
    And the info bar shows "commit abc123 fix" and when the report was generated

    Examples:
      | verdict | score | delta           | shown_delta   |
      | RED     | 62    | -3              |  (-3 vs prev) |
      | GREEN   | 95    | 4               |  (+4 vs prev) |
      | AMBER   | 80    | no previous run |               |

  @id:reporting.html-report.008 @rule:reporting.html-report.not-run-is-not-a-pass @verified @source:src/gandalf/render_html.py#_gate_row @test:tests/test_unavailable.py#test_html_render_labels_them_not_run
  Scenario: Gates that could not run are labelled NOT RUN and give their category no percentage
    Given Gate "ruff" passed
    And And gate "trivy" could not run because the tool is missing
    And And "trivy" is the only gate in its category
    When the operator opens the HTML report
    Then the "trivy" row shows the status "NOT RUN" with the skip marker
    And the score card for trivy's category shows "not run" in place of a percentage
    And the "ruff" row shows its normal pass status

  @id:reporting.html-report.009 @rule:reporting.html-report.gate-table-browsable @verified @source:src/gandalf/render_html.py#render_html @test:tests/test_report.py#test_render_html_has_rag_filter_buttons @test:tests/test_report.py#test_render_html_smoke
  Scenario: The gate table can be filtered by status and lists each gate's findings
    Given Gate "ruff" failed with 1 finding at a.py line 5
    And And gate "mypy" warned
    And And gate "gitleaks" passed
    When the operator opens the HTML report
    Then filter buttons All, Fail, Warn and Pass are shown, with All selected
    And the gate, category and status columns can be sorted
    And rows are first ordered by category and then by gate name
    And the "ruff" row has a collapsible "1 finding" list naming a.py line 5
    And a gate that blocks the verdict carries a "blocking" tag

  @id:reporting.html-report.010 @rule:reporting.html-report.raw-diff-view @verified @source:src/gandalf/render_html.py#_diff_html @test:tests/test_report.py#test_diff_html_empty_is_blank @test:tests/test_report.py#test_diff_html_colors_added_and_removed_lines @test:tests/test_report.py#test_diff_html_ignores_file_header_markers @test:tests/test_report.py#test_render_html_embeds_diff_view @test:tests/test_report.py#test_render_html_without_diff_omits_diff_view
  Scenario Outline: The changeset can be expanded into a coloured raw diff, omitted when nothing changed
    Given The evaluated change has the diff <diff>
    When the operator opens the HTML report
    Then <shown>

    Examples:
      | diff                                            | shown                                                                                                                                                        |
      | "-old line" and "+new line" under a hunk header | a collapsed "View raw diff (3 lines)" section with the removal, the addition and the hunk header each coloured, and the ---/+++ file headers left uncoloured |
      | empty                                           | no raw diff section                                                                                                                                          |
      | longer than 20000 characters                    | only the first 20000 characters, ending in "… (truncated)", while the line count covers the whole diff                                                       |

  @id:reporting.html-report.011 @rule:reporting.html-report.missing-ai-sections-marked @inferred @source:src/gandalf/render_html.py#_advice_section @questionable
  Scenario Outline: AI sections the model did not write are marked as not generated, and an all-clear remediation is left out
    Given The AI write-up returned <returned>
    When the operator opens the HTML report
    Then <section> shows <shown>

    Examples:
      | returned                                 | section                 | shown                                                          |
      | no changeset text                        | the Changeset section   | "Not generated for this run (LLM was skipped or unavailable)." |
      | no improvement text                      | the Improvement section | "Not generated for this run (LLM was skipped or unavailable)." |
      | no remediation text                      | the Remediation section | "Not generated for this run (LLM was skipped or unavailable)." |
      | remediation "**No remediation needed.**" | the Remediation section | nothing: the section is left out                               |
      | no summary text                          | the Summary section     | "(no summary)"                                                 |

  @id:reporting.html-report.012 @rule:reporting.html-report.remediation-failures-first @inferred @source:src/gandalf/render_html.py#_remediation_html @questionable
  Scenario: Remediation advice lists failing gates before warning gates, each labelled with its status
    Given The AI write-up has remediation advice for gates "mypy" and "ruff" and for a gate "legacy" that was not part of this run
    And And gate "mypy" warned
    And And gate "ruff" failed
    When the operator opens the HTML report
    Then the Remediation section lists "ruff" with its fail status before "mypy" with its warn status
    And "legacy" is listed last, labelled "WARN"
    And any introductory remediation text comes before the gate blocks
