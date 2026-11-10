@domain:reporting @area:terminal-scorecard @from:gandalf/summary
Feature: Reading the run footer in the terminal
  Gives the operator who runs gandalf in a terminal the context under the scorecard: which languages were found, which gates were left out, what was autofixed, where the scanners came from, which config was used and why a non-red run still failed.

  Background:
    Given the operator runs gandalf from a terminal on a repository

  @id:reporting.terminal-scorecard.009 @rule:reporting.footer.policy-failure-explained @inferred @source:src/gandalf/summary.py#print_summary
  Scenario Outline: A run that fails on policy without a red light says why
    Given the overall traffic light is <light>
    And the project policy is <policy>
    When the operator runs a check
    Then the footer shows "Policy: run FAILED — <reason>"
    And the command exits with status 1

    Examples:
      | light               | policy       | reason                       |
      | amber               | fail-on=warn | a gate warned (fail-on=warn) |
      | green with score 72 | min-score 80 | score 72 below min-score 80  |

  @id:reporting.terminal-scorecard.010 @rule:reporting.footer.languages-and-left-out-gates @inferred @source:src/gandalf/summary.py#print_summary
  Scenario Outline: The footer lists the detected languages and the gates left out of the run
    Given the repository contains <languages>
    And <skipped> gates were skipped as irrelevant
    And <disabled> gates were disabled
    When the operator runs a check
    Then the footer shows "<line>"

    Examples:
      | languages                  | skipped            | disabled       | line                                                                                               |
      | Python and Go files        | no                 | no             | Languages: go, python                                                                              |
      | no recognised source files | no                 | no             | Languages: none detected                                                                           |
      | Python files               | the eslint and tsc | the well_architected | Languages: python  ·  skipped 2 irrelevant gate(s): eslint, tsc  ·  disabled 1 gate(s): well_architected |

  @id:reporting.terminal-scorecard.011 @rule:reporting.footer.fixes-applied @inferred @source:src/gandalf/summary.py#print_summary @questionable
  Scenario Outline: After autofixing, the footer lists each fixer that changed files
    Given the operator asked gandalf to apply fixes
    And <outcome>
    When the operator runs a check
    Then the footer shows a "Fixes applied:" section
    And the section shows <shown>

    Examples:
      | outcome                                                       | shown                                                 |
      | the ruff fixer rewrote files and reported "ruff: 2 autofixed" | "✔ ruff: 2 autofixed" with the gate name printed once |
      | fixers ran but none changed a file                            | "(none)"                                              |

  @id:reporting.terminal-scorecard.012 @rule:reporting.footer.tool-provenance @verified @source:src/gandalf/summary.py#_tools_line @test:tests/test_tool_provenance.py#test_footer_line_counts_both_sources @test:tests/test_tool_provenance.py#test_no_tools_no_block
  Scenario Outline: The footer says where this run's scanners came from
    Given <host> scanners were found on the PATH and <image> were run from the gandalf-tools image with id sha256:abcdef0123456789
    When the operator runs a check
    Then the footer shows "<line>"

    Examples:
      | host | image | line                                                           |
      | 1    | 1     | Tools: 1 from PATH, 1 from gandalf-tools (sha256:abcdef012345) |
      | 1    | 0     | Tools: 1 from PATH                                             |
      | 0    | 0     | no Tools line                                                  |

  @id:reporting.terminal-scorecard.013 @rule:reporting.footer.tool-versions @verified @source:src/gandalf/summary.py#_versions_block @test:tests/test_tool_provenance.py#test_footer_lists_versions_when_probed
  Scenario: When tool versions are probed, the footer lists each scanner's version
    Given the operator asked for tool versions
    And ruff 0.15.8 was found on the PATH
    When the operator runs a check
    Then under the Tools line the footer shows "  ruff (host) ruff 0.15.8"

  @id:reporting.terminal-scorecard.014 @rule:reporting.footer.config-path @inferred @source:src/gandalf/summary.py#print_summary
  Scenario: The footer names the configuration file the run used
    Given the repository has a gandalf configuration file at .gandalf.toml
    When the operator runs a check
    Then the footer shows "Config: " followed by the full path of that .gandalf.toml
