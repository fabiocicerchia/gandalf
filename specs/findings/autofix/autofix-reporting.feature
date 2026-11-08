@domain:findings @area:autofix @from:gandalf/fixers
Feature: Applying tool fixes and reporting what they rewrote
  Lets an operator run the tools' own autofixers with --fix and see, per gate, which files were actually rewritten, regardless of what each tool prints about itself.

  Background:
    Given the operator's repository is a git working tree
    And the operator runs gandalf with --fix

  @id:findings.autofix.001 @rule:findings.autofix.credit-from-rewritten-files @verified @source:src/gandalf/fixers.py#run_fixers @test:tests/test_run.py#test_fixer_report_comes_from_the_worktree
  Scenario: A fixer is credited with the files it actually rewrote, even when it claims to have changed nothing
    Given the eslint gate is active
    And eslint rewrites src/app.js but reports that it changed nothing
    When the operator runs the check
    Then the eslint fix is reported as changed
    And its message ends with " — src/app.js"
    And "Fixes applied" lists eslint with that message

  @id:findings.autofix.002 @rule:findings.autofix.per-fixer-attribution @inferred @source:src/gandalf/fixers.py#run_fixers
  Scenario: Each fixer is credited only with the files it rewrote itself
    Given the working tree already has an uncommitted edit to README.md
    And the ruff gate rewrites src/a.py
    And the ruff-format gate then rewrites src/b.py
    When the operator runs the check
    Then the ruff fix names src/a.py and not README.md
    And the ruff-format fix names src/b.py and not src/a.py

  @id:findings.autofix.003 @rule:findings.autofix.no-change-reported-as-none @verified @source:src/gandalf/fixers.py#run_fixers @test:tests/test_run.py#test_a_fixer_that_changes_nothing_is_reported_as_such
  Scenario: A fixer that rewrites nothing is reported as not having changed anything
    Given the ruff gate is active
    And ruff finds nothing to fix and rewrites no file
    When the operator runs the check
    Then the JSON report's fixes list ruff with changed false and its own message
    And "Fixes applied" shows "(none)"

  @id:findings.autofix.004 @rule:findings.autofix.failing-fixer-isolated @verified @source:src/gandalf/fixers.py#run_fixers @test:tests/test_run.py#test_run_fixers_isolates_errors
  Scenario: A fixer that crashes is reported as errored and does not stop the other fixers
    Given the shellcheck gate's fixer crashes with the unexpected error "git apply failed"
    And the ruff gate's fixer rewrites src/a.py
    When the operator runs the check
    Then the shellcheck fix is reported with message "fix errored: git apply failed" and changed false
    And the ruff fix is still applied and names src/a.py
    And the check goes on to run the gates

  @id:findings.autofix.005 @rule:findings.autofix.long-file-list-truncated @verified @source:src/gandalf/fixers.py#_files_note @test:tests/test_run.py#test_files_note_lists_and_truncates
  Scenario Outline: A fix that rewrote many files names the first five and counts the rest
    Given the ruff gate rewrites <count> files f0.py to f<last>.py
    When the operator runs the check
    Then the ruff fix message ends with "<suffix>"

    Examples:
      | count | last | suffix                                      |
      | 2     | 1    | f0.py, f1.py                                |
      | 5     | 4    | f0.py, f1.py, f2.py, f3.py, f4.py           |
      | 7     | 6    | f0.py, f1.py, f2.py, f3.py, f4.py, …+2 more |

  @id:findings.autofix.006 @rule:findings.autofix.only-gates-with-fixers @verified @source:src/gandalf/fixers.py#run_fixers @test:tests/test_run.py#test_run_fixers_collects_and_skips
  Scenario: Only active gates that offer a fix are run as fixers and reported
    Given the ruff gate offers a fix
    And the mypy gate offers no fix
    When the operator runs the check
    Then the fixes in the report list ruff
    And the fixes in the report do not list mypy
