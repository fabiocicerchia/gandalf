@domain:findings @area:finding-model @from:gandalf/findings
Feature: Reading findings in one shape across every tool
  Editor plugins and other tools that read the JSON report get every finding's file, line, column, rule, message, severity and documentation link in one standard shape, whatever scanner produced it.

  Background:
    Given a repository checked out at /work/acme-api
    And the operator asked for the JSON report

  @id:findings.finding-model.001 @rule:findings.normalised.block-added-tool-keys-kept @verified @source:src/gandalf/findings.py#annotate @test:tests/test_findings.py#test_annotate_keeps_the_tools_own_keys @test:tests/test_findings.py#test_normalise_shape
  Scenario: Each finding in the JSON report keeps its tool's fields and gains a standard summary
    Given the bandit gate reported a finding with filename "src/c.py", line_number 42, test_id "B105", issue_text "Possible hardcoded password" and issue_severity "HIGH"
    When the operator runs gandalf
    Then the finding in the JSON report still carries test_id "B105" and its other bandit fields unchanged
    And the finding also carries a "_gandalf" block with path "src/c.py", line 42, column 0, rule "B105", message "Possible hardcoded password", severity "high" and url ""
    And a finding the gate reported as plain text rather than as an object is passed through as that text, with no "_gandalf" block

  @id:findings.finding-model.002 @rule:findings.normalised.rule-is-identifier-not-snippet @verified @source:src/gandalf/findings.py#rule @test:tests/test_findings.py#test_bandit_rule_is_the_test_id_not_the_source_snippet @test:tests/test_findings.py#test_rule_reading_across_tools @test:tests/test_findings.py#test_nested_positions
  Scenario Outline: A finding's rule is the tool's rule identifier, never the offending source code
    Given the <tool> gate reported a finding shaped as <tool> publishes it
    When the operator runs gandalf
    Then the finding's "_gandalf" rule is "<rule>"
    And its "_gandalf" line is <line> and column is <column>

    Examples:
      | tool                                                   | rule       | line | column |
      | bandit (test_id B105, code holding the source snippet) | B105       | 42   | 0      |
      | ruff (code E501, location row 12 column 4)             | E501       | 12   | 4      |
      | semgrep (check_id py.lang.x, start line 7 col 3)       | py.lang.x  | 7    | 3      |
      | trivy (VulnerabilityID CVE-2021-1, no line)            | CVE-2021-1 | 0    | 0      |

  @id:findings.finding-model.003 @rule:findings.normalised.severity-ladder @verified @source:src/gandalf/findings.py#severity @test:tests/test_findings.py#test_severity_normalisation @test:tests/test_findings.py#test_every_normalised_severity_is_a_known_level
  Scenario Outline: Severity is reported on one shared scale, and no severity is distinct from an explicit unknown
    Given a gate reported a finding whose severity field reads "<tool severity>"
    When the operator runs gandalf
    Then the finding's "_gandalf" severity is "<severity>"

    Examples:
      | tool severity                                 | severity |
      | CRITICAL                                      | critical |
      | HIGH                                          | high     |
      | Error                                         | high     |
      | moderate                                      | medium   |
      | WARNING (nested under extra, as semgrep does) | medium   |
      | minor                                         | low      |
      | note                                          | low      |
      | informational                                 | info     |
      | UNKNOWN                                       | unknown  |
      | nonsense                                      | (empty)  |
      | (no severity field at all)                    | (empty)  |

  @id:findings.finding-model.004 @rule:findings.normalised.severity-prefix-in-message @verified @source:src/gandalf/findings.py#message_level @test:tests/test_findings.py#test_severity_folded_into_the_message @test:tests/test_findings.py#test_bracket_that_is_not_a_severity_is_left_alone
  Scenario Outline: A severity written in brackets at the start of the message becomes the finding's severity
    Given a gate with no severity field reported the finding "<finding text>"
    When the operator runs gandalf
    Then the finding's "_gandalf" severity is "<severity>"
    And its "_gandalf" message is "<message>"

    Examples:
      | finding text                      | severity | message                           |
      | [HIGH] world-readable secret      | high     | world-readable secret             |
      | [B603] subprocess call            | (empty)  | [B603] subprocess call            |
      | x has no attribute [attr-defined] | (empty)  | x has no attribute [attr-defined] |

  @id:findings.finding-model.005 @rule:findings.normalised.location-from-message-only-if-file-exists @verified @source:src/gandalf/locate.py#place_from_prose @test:tests/test_findings.py#test_location_scraped_from_prose_and_trimmed @test:tests/test_findings.py#test_prose_that_merely_looks_like_a_path_is_not_trusted
  Scenario Outline: A location written in the message is used only when it names a file that exists in the repository
    Given the repository <file exists> a file "src/d.py"
    And a gate reported a finding with no location fields whose text is "<finding text>"
    When the operator runs gandalf
    Then the finding's "_gandalf" path is "<path>" and line is <line>
    And its "_gandalf" message is "<message>"

    Examples:
      | file exists      | finding text                                                         | path     | line | message                                                |
      | contains         | src/d.py:552: error: "Gate" has no attribute "langs"  [attr-defined] | src/d.py | 552  | error: "Gate" has no attribute "langs"  [attr-defined] |
      | does not contain | see docs/missing.md:12 for details                                   | (empty)  | 0    | see docs/missing.md:12 for details                     |

  @id:findings.finding-model.006 @rule:findings.normalised.sentence-in-location-field-is-the-message @verified @source:src/gandalf/findings.py#normalise @test:tests/test_findings.py#test_sentence_in_a_location_key_becomes_the_message
  Scenario: A finding that is only a sentence in a file field is shown as that sentence, anchored to the file it names
    Given the repository contains a file "src/e.py"
    And the format gate reported a finding whose only field is file "Would reformat: src/e.py"
    When the operator runs gandalf
    Then the finding's "_gandalf" message is "Would reformat: src/e.py"
    And its "_gandalf" path is "src/e.py"

  @id:findings.finding-model.007 @rule:findings.normalised.paths-repo-relative @verified @source:src/gandalf/locate.py#relpath @test:tests/test_findings.py#test_relpath_rebases_container_paths @test:tests/test_findings.py#test_fingerprint_vocabulary_is_frozen @questionable
  Scenario Outline: Finding paths are reported relative to the repository root
    Given a gate reported a finding at "<reported path>" while the repository was mounted at "<root>"
    When the operator runs gandalf
    Then the finding's "_gandalf" path is "<path>"

    Examples:
      | reported path                     | root   | path       |
      | /src/a.py                         | /src   | a.py       |
      | ./a.py                            | (none) | a.py       |
      | a\b.py                            | (none) | a/b.py     |
      | alpine:3.1 (a trivy image target) | (none) | alpine:3.1 |
