@domain:reporting @area:badges @from:gandalf/badge
Feature: Publishing a status badge
  Gives repository owners a shields.io endpoint badge for their README that shows the latest gandalf score and verdict colour without gandalf rendering any image.

  Background:
    Given a repository that gandalf has evaluated

  @id:reporting.badges.001 @rule:reporting.badges.score-and-verdict-colour @verified @source:src/gandalf/badge.py#to_badge @test:tests/test_badge.py#test_badge_shape_and_serializable @test:tests/test_badge.py#test_badge_color_follows_rag
  Scenario Outline: The badge shows the score out of 100 in the colour of the verdict
    Given the run's overall verdict is <verdict> with a score of <score>
    When the operator runs gandalf with --badge
    Then the badge file is shields.io endpoint JSON with schemaVersion 1
    And the badge label is "gandalf"
    And the badge message is "<score>/100"
    And the badge colour is "<colour>"

    Examples:
      | verdict | score | colour      |
      | pass    | 92    | brightgreen |
      | warn    | 70    | yellow      |
      | fail    | 20    | red         |

  @id:reporting.badges.002 @rule:reporting.badges.written-only-on-request @inferred @source:src/gandalf/outputs.py#write_outputs
  Scenario Outline: A badge file is written only when asked for, to the default or a chosen path
    Given a run with output stem <stem>
    When the operator runs gandalf <flag>
    Then <outcome>

    Examples:
      | stem      | flag                             | outcome                                                                                                           |
      | repo-main | with --badge                     | the badge is written to reports/repo-main-badge.json and the console prints "Badge: reports/repo-main-badge.json" |
      | repo-main | with --badge public/gandalf.json | the badge is written to public/gandalf.json and the console prints "Badge: public/gandalf.json"                   |
      | repo-main | without --badge                  | no badge file is written and no "Badge:" line is printed                                                          |
