@domain:running-checks @area:scan-scope @from:gandalf/scope
Feature: Choosing what a run evaluates
  Lets an operator point gandalf at the working tree, the staged change, one commit or one folder, so the scorecard judges the change they actually mean.

  Background:
    Given a git repository with tracked files

  @id:running-checks.scan-scope.001 @rule:scope.modes.evaluated-files-and-label @inferred @source:src/gandalf/scope.py#resolve
  Scenario Outline: Each scan mode evaluates its own set of files and names it in the report
    Given the repository has <repo state>
    When the operator runs gandalf <flags>
    Then the gates evaluate <evaluated files>
    And the report's scope reads "<scope label>"

    Examples:
      | repo state                                                                          | flags                     | evaluated files                                                                   | scope label  |
      | tracked files src/app.py and docs/guide.md and an untracked vendor/llama.cpp folder | with no scope flag        | every tracked file in the working tree as it stands, and none of vendor/llama.cpp | working-tree |
      | src/app.py staged and docs/guide.md modified but not staged                         | --staged                  | only src/app.py                                                                   | staged       |
      | commit 3f9c2a1b7d4e5f60 that changed src/app.py against its parent                  | --commit 3f9c2a1b7d4e5f60 | only src/app.py, as it was in that commit                                         | 3f9c2a1b7d   |

  @id:running-checks.scan-scope.002 @rule:scope.staged.empty-index-scans-whole-tree @inferred @source:src/gandalf/scope.py#resolve @questionable
  Scenario: A staged scan with nothing staged evaluates the whole tree
    Given nothing is staged
    And the working tree has tracked files src/app.py and cmd/main.go
    When the operator runs gandalf --staged
    Then the gates evaluate every tracked file, src/app.py and cmd/main.go included
    And the report's scope reads "staged"

  @id:running-checks.scan-scope.003 @rule:scope.commit.no-worktree-left-behind @inferred @source:src/gandalf/scope.py#Scope
  Scenario: Scanning a commit leaves no extra worktree in the user's repository
    Given the operator's working tree has uncommitted edits to src/app.py
    When the operator runs gandalf --commit 3f9c2a1b7d4e5f60
    Then the commit is evaluated in a separate temporary checkout
    And the uncommitted edits to src/app.py are untouched
    And once the run ends, git worktree list shows no gandalf-wt- checkout

  @id:running-checks.scan-scope.004 @rule:scope.commit.unresolvable-commit-fails @inferred @source:src/gandalf/scope.py#resolve @questionable
  Scenario Outline: A commit that cannot be compared against a parent stops the run with a git error
    Given <commit situation>
    When the operator runs gandalf --commit <ref>
    Then the run stops before any gate runs
    And the operator sees a raw git command failure rather than a gandalf message

    Examples:
      | commit situation                                            | ref          |
      | no commit or branch named nosuchbranch exists               | nosuchbranch |
      | a1b2c3d4e5 is the repository's first commit, with no parent | a1b2c3d4e5   |

  @id:running-checks.scan-scope.005 @rule:scope.path.narrows-to-tracked-folder-files @verified @source:src/gandalf/scope.py#_narrow_to_path @test:tests/test_gandalf.py#test_narrow_to_path @test:tests/test_ignore.py#test_path_scope_refuses_to_widen_when_everything_under_it_is_excluded
  Scenario Outline: A path limits the scan to the tracked files under that folder
    Given src/a.py and src/b.py are tracked
    And <mode situation>
    When the operator runs gandalf <flags> --path src
    Then the gates evaluate <evaluated files>
    And the report's scope reads "<scope label>"

    Examples:
      | mode situation                     | flags    | evaluated files       | scope label      |
      | no scope flag is given             |          | src/a.py and src/b.py | working-tree:src |
      | src/a.py and other/c.py are staged | --staged | only src/a.py         | staged:src       |

  @id:running-checks.scan-scope.006 @rule:scope.path.refuses-empty-folder @verified @source:src/gandalf/scope.py#_narrow_to_path @test:tests/test_ignore.py#test_path_scope_refuses_to_widen_when_everything_under_it_is_excluded @test:tests/test_gandalf.py#test_narrow_to_path
  Scenario Outline: A path with nothing to scan is refused instead of scanning everything
    Given <folder state>
    When the operator runs gandalf --path <folder>
    Then the run stops before any gate runs
    And the operator sees "--path '<folder>': <message>"

    Examples:
      | folder state                                          | folder    | message                                |
      | no tracked file lives under nope/                     | nope      | no git-tracked files under this folder |
      | generated/api.py is tracked and generated is excluded | generated | every path under it is excluded        |

  @id:running-checks.scan-scope.007 @rule:scope.repo.requires-git-repository @verified @source:src/gandalf/scope.py#repo_root @test:tests/test_gandalf.py#test_repo_root_reports_git_failure_instead_of_raising
  Scenario Outline: Gandalf refuses to run without git or outside a repository, saying why
    Given <environment>
    When the operator runs gandalf
    Then the run stops before any gate runs
    And the operator sees "<message>" and no traceback

    Examples:
      | environment                                       | message                                                                                 |
      | the current folder is not inside a git repository | gandalf needs a git repository: not a git repository (or any parent of the mount point) |
      | git is not installed on PATH                      | gandalf needs git on PATH, and it is not there                                          |

  @id:running-checks.scan-scope.008 @rule:scope.languages.detected-from-files-in-scope @verified @source:src/gandalf/scope.py#classify @test:tests/test_gandalf.py#test_language_detection @test:tests/test_lang_gates.py#test_language_markers_classify_the_new_ecosystems @test:tests/test_ignore.py#test_languages_reads_the_same_tracked_listing_every_gate_does @test:tests/test_perf.py#test_languages_reuses_that_listing_instead_of_asking_git_again @test:tests/test_perf.py#test_a_scoped_run_never_touches_the_tracked_listing_at_all
  Scenario Outline: Languages are detected from the file names and project markers in scope
    Given the files in scope are <files>
    When the operator runs gandalf
    Then the detected languages are <languages>

    Examples:
      | files                             | languages           |
      | cmd/main.go and go.mod            | go                  |
      | src/app.ts and tsconfig.json      | ts                  |
      | a.py, install.sh and compose.yaml | python, shell, yaml |
      | App/App.csproj and App/Program.cs | dotnet              |
      | src/main.cpp and src/util.h       | cpp, c              |
      | pom.xml                           | java                |
      | src/café.py                       | python              |
      | Dockerfile.prod                   | docker              |
      | README.md                         | none                |
