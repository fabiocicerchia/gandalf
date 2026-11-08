@domain:editor-integrations @area:editor-scans @from:extensions/vscode
Feature: Scanning from the editor
  Lets a developer run gandalf on the workspace, the current file or a commit from VS Code and get the same scorecard CI produces, without breaking on older gandalf builds.

  Background:
    Given the gandalf CLI is installed and can be found by the extension

  @id:editor-integrations.editor-scans.007 @rule:editor.scans.scope-arguments @verified @source:extensions/vscode/src/argv.ts#buildArgs @test:extensions/vscode/src/test/args.test.ts#scopes a file scan with --path, in gandalf’s slash direction @test:extensions/vscode/src/test/args.test.ts#scopes a commit scan with --commit and nothing else @test:extensions/vscode/src/test/args.test.ts#caches only a whole-tree scan @test:extensions/vscode/src/test/args.test.ts#keeps editor scans out of the trend log, and lets a named commit in @test:extensions/vscode/src/test/args.test.ts#asks for HTML only when the run will have a report to show
  Scenario Outline: Each kind of editor scan asks gandalf for its own scope, report and history
    Given a workspace folder that is a git repository
    And the extension setting to use the result cache is on
    When the developer starts a <scan> scan
    Then gandalf is asked to scan <scope>
    And an HTML report is <html>
    And the run is <trend> the score trend log
    And the result cache is <cache>

    Examples:
      | scan                      | scope                    | html        | trend       | cache    |
      | workspace                 | the whole working tree   | written     | kept out of | used     |
      | current file (src\app.py) | the path src/app.py only | not written | kept out of | not used |
      | commit abc1234            | commit abc1234           | written     | recorded in | not used |

  @id:editor-integrations.editor-scans.008 @rule:editor.scans.capability-gated-flags @verified @source:extensions/vscode/src/argv.ts#buildArgs @test:extensions/vscode/src/test/args.test.ts#withholds the flags it knows an older build may not have @test:extensions/vscode/src/test/args.test.ts#puts the user’s own arguments last, so they win
  Scenario: An older gandalf is never handed a flag it does not accept
    Given the installed gandalf's help lists none of --out-dir, --no-trend, --cache, --deadline, --stream or --exclude
    And the developer has set a concurrency of 4 and excludes node_modules
    When the developer scans the workspace
    Then gandalf is not passed --out-dir, --no-trend, --cache, --deadline, --stream or --exclude
    And gandalf is still passed --no-llm and --concurrency 4
    And the developer's own extra arguments come last on the command line

  @id:editor-integrations.editor-scans.009 @rule:editor.scans.deadline-inside-timeout @verified @source:extensions/vscode/src/argv.ts#runArgs @test:extensions/vscode/src/test/args.test.ts#gives gandalf a deadline inside its own timeout, so a long scan still reports @questionable
  Scenario Outline: gandalf is told to stop before the editor gives up on it, so a long scan still produces a scorecard
    Given the scan timeout setting is <timeout> seconds
    And the installed gandalf accepts a deadline
    When the developer scans the workspace
    Then gandalf is given a deadline of <deadline> seconds
    And the extension stops the run itself after <timeout> seconds

    Examples:
      | timeout | deadline |
      | 600     | 580      |
      | 10      | 20       |

  @id:editor-integrations.editor-scans.010 @rule:editor.scans.failed-run-reported @inferred @source:extensions/vscode/src/runner.ts#runGandalf
  Scenario: A run that produced no report is reported as a failure with gandalf's last words
    Given gandalf exits with code 2 and prints no JSON report line
    When the developer scans the workspace
    Then an error "Gandalf: gandalf failed (exit 2): …" is shown quoting the last lines gandalf wrote
    And the notice offers "Show log"
    And the previous scorecard stays on the board

  @id:editor-integrations.editor-scans.011 @rule:editor.scans.empty-scope-silent @inferred @source:extensions/vscode/src/runner.ts#runGandalf
  Scenario: A scan whose scope holds nothing to scan ends quietly
    Given gandalf reports there are no git-tracked files under the requested path
    When the developer scans the current file
    Then no error is shown
    And the log records "scan skipped: … nothing in scope to scan"

  @id:editor-integrations.editor-scans.012 @rule:editor.report.no-network-access @inferred @source:extensions/vscode/src/report.ts#ReportView
  Scenario: The scorecard opened in the editor cannot reach the network, and its links open in the browser
    Given a workspace scan has written an HTML report
    When the developer opens the report
    Then the report is shown in an editor tab titled "Gandalf — <scope>"
    And the report may load no remote script, style or image
    And following an external link in it opens that link in the system browser

  @id:editor-integrations.editor-scans.013 @rule:editor.report.export @inferred @source:extensions/vscode/src/commands.ts#exportReport
  Scenario: The developer can save the scorecard where they choose
    Given no report has been produced yet in this window
    When the developer exports the report
    Then a workspace scan runs first
    And a save dialog offers the report's file name inside the workspace folder, filtered to HTML
    And the confirmation "Gandalf: report exported to <name>." offers "Open"
