@domain:reporting @area:html-report @from:gandalf/html-assets
Feature: Reading the HTML scorecard
  Lets a reviewer open the gandalf HTML report anywhere (CI artifact, email attachment, local file) and switch its theme, sort it and filter it to find the gates that need attention.

  Background:
    Given a gandalf run has produced an HTML report

  @id:reporting.html-report.001 @rule:reporting.html.self-contained @inferred @source:src/gandalf/render_html.py#render_html
  Scenario: The HTML report opens with nothing to fetch
    Given the reviewer has no network access
    When the reviewer opens the HTML report from a file on disk
    Then the report is fully styled
    And the theme toggle, column sorting and status filters work
    And the report loads no stylesheet, script or font from anywhere else

  @id:reporting.html-report.002 @rule:reporting.html.theme-follows-system-until-chosen @inferred @source:src/gandalf/html_assets.py#JS
  Scenario Outline: The report follows the system colour scheme until the reader picks a theme, and remembers that pick
    Given the reader's system prefers the <system> colour scheme
    And the reader has <history>
    When the reader opens an HTML report
    Then the report is shown in the <shown> theme
    And the theme button shows <icon>

    Examples:
      | system | history                                                    | shown | icon   |
      | dark   | never toggled the theme                                    | dark  | a sun  |
      | light  | never toggled the theme                                    | light | a moon |
      | dark   | switched a gandalf report to light earlier in this browser | light | a moon |
      | light  | switched a gandalf report to dark earlier in this browser  | dark  | a sun  |

  @id:reporting.html-report.003 @rule:reporting.html.gate-table-sortable @inferred @source:src/gandalf/html_assets.py#JS @questionable
  Scenario Outline: The reader can sort the gate table by gate, category or status
    Given the gate table lists gates with a mix of Pass, Warn and Fail statuses
    When the reader clicks the <column> column header <clicks>
    Then the rows are ordered <order>
    And the <column> header shows the <arrow> arrow and the other headers show no arrow

    Examples:
      | column   | clicks | order                                                    | arrow |
      | Status   | once   | failures first, then warnings, then passes               | ▼     |
      | Status   | twice  | passes first, then warnings, then failures               | ▲     |
      | Gate     | once   | by gate name A to Z                                      | ▲     |
      | Gate     | twice  | by gate name Z to A                                      | ▼     |
      | Category | once   | by category A to Z, gates within a category A to Z       | ▲     |
      | Category | twice  | by category Z to A, gates within a category still A to Z | ▼     |

  @id:reporting.html-report.004 @rule:reporting.html.gate-table-filter-by-status @verified @source:src/gandalf/html_assets.py#JS @test:tests/test_report.py#test_render_html_has_rag_filter_buttons @questionable
  Scenario Outline: The reader can narrow the gate table to failing, warning or passing gates
    Given the gate table lists a failing gate "bandit", a warning gate "mypy", a passing gate "ruff" and a gate "trivy" shown as NOT RUN
    When the reader selects the <filter> status filter
    Then only <visible> are listed
    And the <filter> filter is highlighted as the active one

    Examples:
      | filter | visible                      |
      | Fail   | bandit                       |
      | Warn   | mypy and trivy               |
      | Pass   | ruff                         |
      | All    | bandit, mypy, ruff and trivy |
