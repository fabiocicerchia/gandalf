@domain:developer-tooling @area:benchmarks @from:scripts/chart
Feature: Charting benchmark results
  Maintainers publishing gandalf's performance numbers get one self-contained SVG figure that compares the shipped code against the implementation it replaced, so readers of the docs or README can see where in-process time and memory go.

  Background:
    Given the maintainer has benchmark measurements, each with a label, a unit, a current value and optionally a previous-implementation value

  @id:developer-tooling.benchmarks.001 @rule:benchmarks.chart.time-and-memory-in-separate-panels @inferred @source:scripts/chart.py#render
  Scenario Outline: Time and peak memory are drawn in separate panels, each on its own scale
    Given measurements in <units>
    When the maintainer draws the benchmark chart
    Then the chart shows the panels <panels>, in that order
    And each panel has its own axis of five ticks starting at 0
    And measurements in any other unit do not appear in the chart

    Examples:
      | units           | panels                 |
      | ms and MiB peak | Time, then Peak memory |
      | ms only         | Time                   |
      | MiB peak only   | Peak memory            |

  @id:developer-tooling.benchmarks.002 @rule:benchmarks.chart.before-and-after-bars @inferred @source:scripts/chart.py#_row_svg
  Scenario Outline: A measurement with a previous implementation shows both bars, one without shows only the current bar
    Given a measurement "<label>" of <after> with previous value <before>
    When the maintainer draws the benchmark chart
    Then the row "<label>" shows <bars>
    And each bar is labelled with its value

    Examples:
      | label        | after | before | bars                                                               |
      | tree filter  | 12.5  | 48.0   | an orange previous-implementation bar above a blue as-it-ships bar |
      | report write | 3.2   | none   | a single blue as-it-ships bar                                      |

  @id:developer-tooling.benchmarks.003 @rule:benchmarks.chart.improvement-factor-shown-above-threshold @inferred @source:scripts/chart.py#_row_svg @questionable
  Scenario Outline: The improvement factor is shown only when the previous implementation was at least 1.15 times the current cost
    Given a measurement with a previous value of <before> and a current value of <after>
    When the maintainer draws the benchmark chart
    Then the end of the row shows <factor>

    Examples:
      | before | after | factor    |
      | 48.0   | 12.0  | 4.0x      |
      | 11.5   | 10.0  | 1.1x      |
      | 10.0   | 10.0  | no factor |
      | 10.0   | 20.0  | no factor |
      | 5.0    | 0     | no factor |

  @id:developer-tooling.benchmarks.004 @rule:benchmarks.chart.self-contained-theme-aware-svg @inferred @source:scripts/chart.py#render
  Scenario: The chart is a single self-contained SVG that follows the reader's light or dark preference
    Given benchmark measurements to chart
    When the maintainer runs the benchmark with an SVG output path
    Then the file at that path is one SVG image with its styles inline and no external stylesheet, script or font
    And it uses the light palette by default and the dark palette when the viewer prefers a dark colour scheme
    And it is titled "Where a scan's in-process time and memory go"
