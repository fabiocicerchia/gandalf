@domain:developer-tooling @area:build-and-install @from:gandalf/makefile
Feature: Installing and running gandalf from a checkout
  Lets an operator discover the repo's make verbs, put a `gandalf` command on their PATH and side-load the editor extension, with clear refusals when a prerequisite is missing.

  Background:
    Given the operator has a checkout of the gandalf repository

  @id:developer-tooling.build-and-install.001 @rule:developer-tooling.make.help-is-default @inferred @source:Makefile#help @questionable
  Scenario: Running make with no target lists the available verbs by group
    When the operator runs make with no target
    Then the output lists every documented target with its one-line description
    And targets appear under the headings "General", "Run", "Quality" and "VS Code extension"
    And no build or scan is started

  @id:developer-tooling.build-and-install.002 @rule:developer-tooling.install.wrapper-on-path @inferred @source:Makefile#install
  Scenario Outline: Installing puts a gandalf command in the chosen bin directory that runs the checkout
    Given the bin directory is <bindir>
    When the operator runs make install<override>
    Then an executable file named gandalf exists in <bindir>
    And the message "installed <bindir>/gandalf" is shown
    And running that gandalf command with any arguments runs gandalf from this checkout with those arguments

    Examples:
      | override               | bindir         |
      |                        | ~/.local/bin   |
      |  BINDIR=/opt/tools/bin | /opt/tools/bin |

  @id:developer-tooling.build-and-install.003 @rule:developer-tooling.extension.install-refused-without-editor-cli @inferred @source:Makefile#ext-install
  Scenario Outline: Installing the editor extension is refused with guidance when the editor's command-line tool is missing
    Given the extension has been packaged
    And no command named <cli> is on the PATH
    When the operator runs make ext-install<override>
    Then the message "'<cli>' CLI not found" is shown
    And the operator is told to install the <cli> command from the Command Palette, or to install the .vsix by hand via "Install from VSIX..."
    And make exits with a failure and the extension is not installed

    Examples:
      | override     | cli    |
      |              | code   |
      |  CODE=cursor | cursor |

  @id:developer-tooling.build-and-install.004 @rule:developer-tooling.extension.build-refused-without-npm @inferred @source:Makefile#ext-build
  Scenario: Building the editor extension is refused when Node's package manager is missing
    Given npm is not installed
    When the operator runs make ext-build
    Then the message "npm not found — Node 18+ is needed to build the extension" is shown
    And make exits with a failure and no extension is built

  @id:developer-tooling.build-and-install.005 @rule:developer-tooling.run.shows-usage-not-scan @inferred @source:Makefile#run @questionable
  Scenario: The run verb prints gandalf's usage instead of scanning the working tree
    When the operator runs make run
    Then gandalf's command-line usage is printed
    And no scan of the working tree takes place and no scorecard is shown
