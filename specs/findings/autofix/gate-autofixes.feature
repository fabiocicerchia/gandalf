@domain:findings @area:autofix @from:gandalf/gates
Feature: Fixing findings in place and suggesting fixes
  Lets developers have gandalf apply the fixes the tools are sure of, and offers fixable lint findings as one-click suggestions.

  Background:
    Given the scan scope is the working tree

  @id:findings.autofix.007 @rule:autofix.ruff.reports-fixed-count @inferred @source:src/gandalf/gates/ruff.py#RuffGate
  Scenario: Ruff's autofix reports how many findings it fixed
    Given the Python in scope has 5 ruff findings, 3 of them auto-fixable
    When the operator runs gandalf with --fix
    Then the 3 fixable findings are rewritten in place
    And the fix line for ruff reads "ruff: 3 finding(s) autofixed"

  @id:findings.autofix.008 @rule:autofix.shellcheck.all-or-nothing @inferred @source:src/gandalf/gates/polyglot.py#ShellcheckGate
  Scenario Outline: Shellcheck's suggested fixes are applied in full or not at all
    Given the repository's shell scripts have shellcheck findings where <situation>
    When the operator runs gandalf with --fix
    Then <files>
    And the fix line for shellcheck reads "<message>"

    Examples:
      | situation                              | files                     | message                                        |
      | shellcheck offers a patch that applies | the scripts are rewritten | shellcheck: applied its suggested fixes        |
      | shellcheck's patch does not apply      | no script is changed      | shellcheck: patch rejected — <git apply error> |
      | shellcheck has nothing it can fix      | no script is changed      | shellcheck: nothing it can fix automatically   |

  @id:findings.autofix.009 @rule:autofix.codespell.only-scored-files @inferred @source:src/gandalf/gates/polyglot.py#CodespellGate
  Scenario: Spelling fixes touch only the files the spelling gate scored, and only certain corrections
    Given tracked files contain 2 unambiguous typos and 1 typo with several possible corrections
    And package-lock.json, app.min.js and logo.svg contain typos
    When the operator runs gandalf with --fix
    Then the 2 unambiguous typos are corrected in place
    And the ambiguous typo is left alone
    And package-lock.json, app.min.js and logo.svg are unchanged
    And the fix line for codespell reads "codespell: 2 typo(s) corrected"

  @id:findings.autofix.010 @rule:autofix.clippy.fixes-uncommitted-work @inferred @source:src/gandalf/gates/rust.py#ClippyGate
  Scenario: Clippy's fixes apply to a checkout with uncommitted changes
    Given a Rust crate with uncommitted edits that trigger machine-applicable clippy lints
    When the operator runs gandalf with --fix
    Then the lints are fixed in the uncommitted files
    And the fix line for clippy reads "clippy --fix applied"
    And if cargo cannot finish, it reads "clippy --fix: did not complete — <cargo error>"

  @id:findings.autofix.011 @rule:autofix.suggestions.eslint-fix-as-edit @verified @source:src/gandalf/gates/node.py#_messages @test:tests/test_gandalf.py#test_eslint_messages_carry_a_normalised_fix @test:tests/test_gandalf.py#test_eslint_messages_survive_junk
  Scenario: A fixable lint finding carries its fix as a line-and-column suggested edit
    Given a.js line 1 reads "const a = 1" and eslint reports a missing semicolon it can fix
    When the operator runs gandalf
    Then the "eslint" finding for a.js carries a suggested edit inserting ";" at line 1, column 12
    And a finding eslint cannot fix carries no suggested edit and is reported under rule "eslint" when it names no rule
