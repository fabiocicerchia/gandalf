@domain:quality-gates @area:code-health @from:gandalf/gates
Feature: Flagging complexity, documentation and style smells
  Shows maintainers cosmetic and maintainability issues without letting pure style failures redden a release.

  Background:
    Given the tool each gate needs is installed on the host or in the gandalf-tools image

  @id:quality-gates.code-health.001 @rule:code-health.smells.capped-at-amber @inferred @source:src/gandalf/gates/lizard.py#LizardGate
  Scenario Outline: Complexity, dead code, spelling, formatting, Markdown and migration findings never turn a gate red
    Given the "<gate>" tool reports <findings>
    When the operator runs gandalf
    Then the "<gate>" gate is amber, not red
    And its summary reads "<summary>"

    Examples:
      | gate      | findings                        | summary                                          |
      | lizard    | 25 over-complex functions       | lizard: 25 function(s) over complexity threshold |
      | vulture   | 50 unused items                 | vulture: 50 unused item(s)                       |
      | codespell | 40 typos                        | codespell: 40 typo(s)                            |
      | format    | 12 files that need reformatting | format: 12 file(s) need formatting               |
      | mdl       | 30 Markdown style issues        | mdl: 30 issue(s)                                 |
      | squawk    | 15 unsafe migration statements  | squawk: 15 migration warning(s)                  |

  @id:quality-gates.code-health.002 @rule:code-health.docstrings.coverage-threshold @inferred @source:src/gandalf/gates/interrogate.py#InterrogateGate
  Scenario Outline: Docstring coverage below the configured minimum turns the gate amber
    Given GANDALF_DOCSTRING_MIN is <minimum>
    And the Python in scope has <coverage>% docstring coverage
    When the operator runs gandalf
    Then the "interrogate" gate is <colour> with score <score>
    And its summary reads "<summary>"

    Examples:
      | minimum    | coverage | colour | score | summary                         |
      | unset (60) | 72       | green  | 0.72  | docstring coverage 72% (>= 60%) |
      | unset (60) | 45       | amber  | 0.45  | docstring coverage 45% (< 60%)  |
      | 80         | 72       | amber  | 0.72  | docstring coverage 72% (< 80%)  |

  @id:quality-gates.code-health.003 @rule:code-health.docstrings.no-report-reads-pass @inferred @source:src/gandalf/gates/interrogate.py#InterrogateGate @questionable
  Scenario: A docstring check that prints no coverage figure reads as a clean pass
    Given the repository contains Python
    And interrogate exits without printing its coverage result
    When the operator runs gandalf
    Then the "interrogate" gate is green with score 1.0
    And its summary reads "interrogate: no Python to document"

  @id:quality-gates.code-health.004 @rule:code-health.config-lint.errors-turn-red @inferred @source:src/gandalf/gates/polyglot.py#ShellcheckGate
  Scenario Outline: Shell, YAML, workflow, Dockerfile and SQL lint turn red on errors or volume, amber otherwise
    Given the "<gate>" tool reports <findings>
    When the operator runs gandalf
    Then the "<gate>" gate is <colour>
    And its summary reads "<summary>"

    Examples:
      | gate       | findings                  | colour | summary                                 |
      | shellcheck | 1 error-level issue       | red    | shellcheck: 1 issue(s), 1 error(s)      |
      | shellcheck | 2 warning-level issues    | amber  | shellcheck: 2 issue(s), 0 error(s)      |
      | yamllint   | 1 [error] line            | red    | yamllint: 1 issue(s), 1 error(s)        |
      | yamllint   | 5 warnings                | amber  | yamllint: 5 issue(s), 0 error(s)        |
      | actionlint | 3 issues                  | amber  | actionlint: 3 issue(s)                  |
      | actionlint | 4 issues                  | red    | actionlint: 4 issue(s)                  |
      | hadolint   | 1 error in one Dockerfile | red    | hadolint: 1 issue(s) in 1 Dockerfile(s) |
      | sqlfluff   | 10 lint issues            | amber  | sqlfluff: 10 lint issue(s)              |
      | sqlfluff   | 11 lint issues            | red    | sqlfluff: 11 lint issue(s)              |

  @id:quality-gates.code-health.005 @rule:code-health.no-files-green-skip @inferred @source:src/gandalf/gates/mdl.py#MdlGate
  Scenario Outline: A gate with no files of its kind in the repository is a green skip
    Given the repository's tracked files include <content>
    When the operator runs gandalf
    Then the "<gate>" gate is green with summary "<summary>"

    Examples:
      | gate       | content                               | summary                        |
      | mdl        | no Markdown                           | mdl: no markdown files         |
      | mdl        | only .github/pull_request_template.md | mdl: no markdown files         |
      | sqlfluff   | no .sql files                         | sqlfluff: no SQL files         |
      | squawk     | no .sql files                         | squawk: no SQL files           |
      | shellcheck | no .sh or .bash files                 | shellcheck: no shell scripts   |
      | hadolint   | no Dockerfile                         | hadolint: no Dockerfiles found |
      | actionlint | no .github/workflows                  | actionlint: no workflows       |
