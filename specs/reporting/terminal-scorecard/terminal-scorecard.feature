@domain:reporting @area:terminal-scorecard @from:gandalf/render-text
Feature: Reading the scorecard in the terminal
  Gives the developer or CI operator who runs gandalf the verdict, per-category gate results, remediation advice and setup guidance right in the terminal, so they don't have to open the HTML or JSON report.

  Background:
    Given the operator runs gandalf in a terminal

  @id:reporting.terminal-scorecard.001 @rule:reporting.terminal.verdict-banner @verified @source:src/gandalf/render_text.py#render_terminal @test:tests/test_report.py#test_render_terminal_smoke @test:tests/test_report.py#test_render_terminal_shows_delta @test:tests/test_setup_banner.py#test_verdict_line_is_normal_when_something_ran
  Scenario Outline: The scorecard leads with the traffic light, the score and the change since the previous commit
    Given at least one gate produced a result
    And the overall verdict is <light> with a score of <score>
    And the previous commit scored <delta> points differently
    When the operator runs a check
    Then the scorecard heading reads "GANDALF — <scope>"
    And the verdict line reads "<light> · <score>/100<delta_text>"

    Examples:
      | light | score | delta          | delta_text    | scope          |
      | GREEN | 100   | no prior score |               | working-tree   |
      | AMBER | 67    | -7             |  (-7 vs prev) | staged         |
      | RED   | 42    | +5             |  (+5 vs prev) | abc1234def     |

  @id:reporting.terminal-scorecard.002 @rule:reporting.terminal.no-score-when-nothing-ran @verified @source:src/gandalf/render_text.py#render_terminal @test:tests/test_setup_banner.py#test_verdict_line_does_not_claim_a_zero_score_when_nothing_ran
  Scenario: A run where no gate could run shows NOT RUN instead of a score
    Given every gate reported that it could not run
    When the operator runs a check
    Then the verdict line reads "NOT RUN · no gate produced a result"
    And no "0/100" score is shown

  @id:reporting.terminal-scorecard.003 @rule:reporting.terminal.gates-grouped-by-category @inferred @source:src/gandalf/render_text.py#render_terminal
  Scenario: Gates are listed under their category, with the category's worst light and average score
    Given the gates "gitleaks" (Security, passed, 100%) and "bandit" (Security, warned, 60%) produced results
    And the gate "ruff" (Code quality) is blocking and failed
    When the operator runs a check
    Then each category that has gates gets a heading, in the fixed category order, coloured by its worst gate light and followed by its average score, e.g. "Security · 80%"
    And a category whose gates all could not run shows "not run" instead of a percentage
    And each gate row shows its traffic-light dot, its name and its summary
    And a blocking gate's row ends with "[blocking]"

  @id:reporting.terminal-scorecard.004 @rule:reporting.terminal.unrun-gates-marked-and-counted @verified @source:src/gandalf/render_text.py#render_terminal @test:tests/test_unavailable.py#test_terminal_render_marks_and_counts_them
  Scenario: Gates that could not run are marked apart and counted outside the score
    Given the gate "ruff" passed
    And the gate "trivy" could not run because its scanner is missing
    When the operator runs a check
    Then the "trivy" row shows a white dot instead of a traffic light
    And the scorecard notes "1 of 2 gate(s) could not run — not counted in the score"

  @id:reporting.terminal-scorecard.005 @rule:reporting.terminal.remediation-worst-first @inferred @source:src/gandalf/render_text.py#_remediation_text @questionable
  Scenario: Remediation advice lists failing gates before warning gates
    Given the AI summary gave remediation advice for the gates "mypy" (warned) and "ruff" (failed)
    When the operator runs a check
    Then the REMEDIATION section lists "ruff (RED):" before "mypy (AMBER):"
    And the advice for a gate whose outcome is unknown comes last, labelled "(WARN)"
    And without per-gate advice, the REMEDIATION section shows the summary's remediation text as given

  @id:reporting.terminal-scorecard.006 @rule:reporting.terminal.score-explanation @verified @source:src/gandalf/render_text.py#explain_score @test:tests/test_explain_score.py#test_lists_every_counted_gate_with_its_contribution @test:tests/test_explain_score.py#test_names_the_gates_left_out_and_why @test:tests/test_explain_score.py#test_shows_the_gates_own_score_when_severity_reweighted @test:tests/test_explain_score.py#test_no_note_when_reweighting_changed_nothing @test:tests/test_explain_score.py#test_nothing_ran_says_so_rather_than_averaging_nothing @test:tests/test_explain_score.py#test_the_arithmetic_shown_is_the_arithmetic_used
  Scenario: Asking to explain the score shows each counted gate's contribution and the mean behind it
    Given the gates "ruff" (score 1.0) and "mypy" (score 0.5) produced results
    And the gate "trivy" could not run
    When the operator runs a check with --explain-score
    Then a SCORE section shows "75/100"
    And "ruff" is shown contributing 50.0 and "mypy" contributing 25.0
    And the gate table closes with "2 gate(s) counted · mean 0.750 → 75/100"
    And the section then notes "1 not counted (could not run): trivy"
    And a gate whose score was changed by severity weighting also shows the score the gate itself gave, e.g. "(gate scored 0.90, severity-weighted)"
    And when no gate ran, it says there is nothing to average

  @id:reporting.terminal-scorecard.007 @rule:reporting.terminal.setup-banner-threshold @verified @source:src/gandalf/render_text.py#setup_banner @test:tests/test_setup_banner.py#test_no_banner_when_the_run_said_something_useful @test:tests/test_setup_banner.py#test_banner_when_most_gates_could_not_run @test:tests/test_setup_banner.py#test_banner_when_nothing_ran_at_all @test:tests/test_setup_banner.py#test_empty_results_never_banner
  Scenario Outline: A setup banner appears only when at least two thirds of the gates could not run
    Given <missing> of <total> gates could not run because their scanners are missing
    When the operator runs a check
    Then <banner>

    Examples:
      | missing | total | banner                                                                                                                                    |
      | 4       | 14    | no setup banner is shown                                                                                                                  |
      | 9       | 10    | a setup banner reads "Most scanners are unavailable — 9 of 10 gates could not run."                                                       |
      | 12      | 12    | a setup banner reads "No scanners available — gandalf checked nothing." and "Nothing was verified, so the score is not a quality signal." |
      | 0       | 0     | no setup banner is shown                                                                                                                  |

  @id:reporting.terminal-scorecard.008 @rule:reporting.terminal.setup-advice-fits-host @verified @source:src/gandalf/render_text.py#setup_banner @test:tests/test_setup_banner.py#test_advice_matches_what_is_actually_missing @test:tests/test_setup_banner.py#test_banner_when_most_gates_could_not_run
  Scenario Outline: The setup banner's advice depends on what the host already has
    Given most gates could not run because their scanners are missing
    And the scanner-tools image is <image>, and Docker is <docker>
    When the operator runs a check
    Then the setup banner advises: <advice>

    Examples:
      | image     | docker        | advice                                                                                          |
      | built     | installed     | install the host-only language toolchains (go, npx/npm, cargo, mvn); no mention of make tools   |
      | not built | installed     | build the scanner image once with "make tools", or install scanners on PATH                     |
      | not built | not installed | install the scanners on PATH, or install Docker and run "make tools"; the image is never pulled |
