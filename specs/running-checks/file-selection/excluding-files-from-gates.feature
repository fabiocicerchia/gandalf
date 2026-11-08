@domain:running-checks @area:file-selection @from:gandalf/ignores
Feature: Excluding files from what every gate scans
  Lets an operator keep vendored, generated and build output out of every gate's scan, through built-in defaults, a repository .gandalfignore and --exclude, so scores reflect the repository's own source.

  Background:
    Given a git repository with committed files

  @id:running-checks.file-selection.001 @rule:file-selection.ignores.default-noise-skipped @verified @source:src/gandalf/ignores.py#ignore_patterns @test:tests/test_ignore.py#test_defaults_and_gandalfignore_and_exclude_all_land_in_one_list
  Scenario Outline: Build, vendor and report folders are skipped without any configuration
    Given the repository has no .gandalfignore
    And no --exclude patterns are given
    And the repository tracks "src/app.py" and "<noise_path>"
    When the operator runs a whole-tree check
    Then the gates scan "src/app.py"
    And the gates do not scan "<noise_path>"

    Examples:
      | noise_path                      |
      | reports/latest.json             |
      | web/node_modules/react/index.js |
      | llama.cpp/main.c                |
      | .venv/lib/site.py               |

  @id:running-checks.file-selection.002 @rule:file-selection.ignores.pattern-forms @verified @source:src/gandalf/ignores.py#is_ignored @test:tests/test_ignore.py#test_is_ignored @test:tests/test_ignore.py#test_is_ignored_takes_any_matching_pattern
  Scenario Outline: An exclusion can be a folder name, a root-anchored path or a glob
    Given the exclusion "<pattern>" is configured
    When the operator runs a check that would include "<path>"
    Then "<path>" is <outcome> by every gate

    Examples:
      | pattern       | path                            | outcome |
      | node_modules  | web/node_modules/react/index.js | skipped |
      | node_modules  | node_modules_old/a.js           | scanned |
      | src/generated | src/generated/api.py            | skipped |
      | src/generated | lib/src/generated/api.py        | scanned |
      | *.min.js      | web/static/app.min.js           | skipped |
      | *.min.js      | web/static/app.js               | scanned |
      | vendor/*      | vendor/jquery/dist/a.js         | skipped |
      | Thumbs.db     | assets/Thumbs.db                | skipped |
      | data/         | data/dump.sql                   | skipped |
      | ./data        | data/dump.sql                   | skipped |

  @id:running-checks.file-selection.003 @rule:file-selection.ignores.sources-combine @verified @source:src/gandalf/ignores.py#ignore_patterns @test:tests/test_ignore.py#test_defaults_and_gandalfignore_and_exclude_all_land_in_one_list
  Scenario: Exclusions from .gandalfignore and --exclude add to the defaults
    Given the repository's .gandalfignore contains a comment line, a blank line and "data/"
    And the operator passes --exclude "*.min.js" and a blank --exclude value
    When the operator runs a check
    Then files under "data/" are skipped
    And files matching "*.min.js" are skipped
    And the built-in default folders are still skipped
    And the comment and blank lines exclude nothing

  @id:running-checks.file-selection.004 @rule:file-selection.scope.whole-tree-is-tracked-minus-excluded @verified @source:src/gandalf/ignores.py#scan_targets @test:tests/test_ignore.py#test_exclusions_narrow_what_every_gate_scans
  Scenario: A whole-tree check scans only tracked files that are not excluded
    Given the repository tracks "src/app.py", "src/generated/api.py", "vendor/lib.py" and "web/app.min.js"
    And the .gandalfignore contains "src/generated"
    And an untracked file "scratch/notes.py" exists in the working tree
    When the operator runs a check with --exclude "vendor" and --exclude "*.min.js"
    Then the gates scan ".gandalfignore" and "src/app.py"
    And the gates do not scan "src/generated/api.py", "vendor/lib.py" or "web/app.min.js"
    And the gates do not scan "scratch/notes.py"

  @id:running-checks.file-selection.005 @rule:file-selection.scope.changed-set-respects-exclusions @verified @source:src/gandalf/ignores.py#_changed_in_scope @test:tests/test_ignore.py#test_exclusions_apply_to_a_changed_set_too
  Scenario: A check of a change scans only the changed files that still exist and are not excluded
    Given the change touches "src/app.py" and "src/generated/api.py"
    And the change deletes "src/old.py"
    When the operator runs a check of the change with --exclude "src/generated"
    Then the gates scan only "src/app.py"

  @id:running-checks.file-selection.006 @rule:file-selection.scope.empty-change-widens-to-tree @inferred @source:src/gandalf/ignores.py#scan_targets @questionable
  Scenario: A change made up only of excluded or deleted files is scanned as the whole tree
    Given the repository tracks "src/app.py" and "generated/api.py"
    And the staged change touches only "generated/api.py"
    When the operator runs a check of the staged change with --exclude "generated"
    Then the gates scan "src/app.py" and every other tracked, non-excluded file

  @id:running-checks.file-selection.007 @rule:file-selection.scope.non-git-scans-directory @inferred @source:src/gandalf/ignores.py#scan_targets @questionable
  Scenario: Outside a git repository a whole-tree check scans the whole directory
    Given the directory being checked is not a git repository
    And the directory contains "src/app.py" and "node_modules/react/index.js"
    When the operator runs a whole-tree check
    Then the gates are pointed at the entire directory instead of at a list of files
