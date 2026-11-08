@domain:editor-integrations @area:editor-scans @from:extensions/nvim
Feature: Scanning a project from Neovim
  Lets a developer run gandalf from inside Neovim on the workspace, the current file or a commit, without hanging the editor or flooding the machine with concurrent runs.

  Background:
    Given the gandalf Neovim plugin is installed in a git project
    And the configured gandalf command is installed

  @id:editor-integrations.editor-scans.001 @rule:nvim.scans.unsupported-flags-withheld @verified @source:extensions/nvim/lua/gandalf/capabilities.lua#M.of @test:extensions/nvim/tests/core_spec.lua#withholds every optional flag the build did not report @test:extensions/nvim/tests/core_spec.lua#still passes the flags gandalf has always had @test:extensions/nvim/tests/core_spec.lua#passes them all when the build reported them, and when nobody probed @questionable
  Scenario Outline: Optional flags an older gandalf does not advertise are left off
    Given the installed gandalf's --help names <advertised>
    When the developer starts a workspace scan
    Then "--out-dir", "--no-trend", "--cache", "--stream" and "--exclude" (for each configured exclude) are passed <optional flags>
    And "--no-llm" and "--no-html" are passed whatever --help says

    Examples:
      | advertised                            | optional flags |
      | none of the optional flags            | not at all     |
      | all of the optional flags             | all            |
      | nothing, because --help failed to run | all            |

  @id:editor-integrations.editor-scans.002 @rule:nvim.scans.one-run-at-a-time @verified @source:extensions/nvim/lua/gandalf/scan.lua#may_start @test:extensions/nvim/tests/init_spec.lua#never queues an automatic scan behind a running one @test:extensions/nvim/tests/init_spec.lua#lets a manual scan preempt the one in flight, and kills what it preempted @questionable
  Scenario Outline: Only one gandalf run happens at a time, and a manual scan replaces an automatic one
    Given a scan is already running
    When a <second scan> is requested
    Then <outcome>
    And the log <log line>

    Examples:
      | second scan                      | outcome                                                    | log line                            |
      | automatic scan after a save      | no second gandalf process is started                       | records no "preempting" entry       |
      | manual scan from :GandalfScanAll | the running gandalf process is killed and a new run starts | reads "preempting the running scan" |

  @id:editor-integrations.editor-scans.003 @rule:nvim.scans.no-report-is-a-failure @verified @source:extensions/nvim/lua/gandalf/scan.lua#on_exit @test:extensions/nvim/tests/init_spec.lua#fails the run when no report line was printed @test:extensions/nvim/tests/init_spec.lua#quotes the end of stderr, which is where a dying process writes why @test:extensions/nvim/tests/init_spec.lua#fails the run when the report it named is not readable JSON @test:extensions/nvim/tests/init_spec.lua#says the command could not be run at all
  Scenario Outline: A run that leaves no readable report is reported as a failed scan
    Given <situation>
    When the developer runs :GandalfScanAll
    Then an error notification reads "Gandalf: <message>"
    And the log records "scan failed"
    And the previous scorecard stays in place

    Examples:
      | situation                                                                                | message                                                |
      | gandalf exits 1 printing "gandalf: exploded" as its last stderr line and names no report | gandalf produced no report (exit 1): gandalf: exploded |
      | gandalf names a report file that is not valid JSON                                       | could not read the report gandalf wrote at <path>      |
      | the configured command cannot be started                                                 | could not run `<command>` — see :checkhealth gandalf   |

  @id:editor-integrations.editor-scans.004 @rule:nvim.scans.cancel-running-scan @verified @source:extensions/nvim/lua/gandalf/scan.lua#M.cancel @test:extensions/nvim/tests/init_spec.lua#cancelling clears the run without failing it @questionable
  Scenario Outline: Cancelling stops the running gandalf process
    Given <running state>
    When the developer runs :GandalfCancel
    Then the notification reads "Gandalf: <message>"
    And the status line no longer reports a scan in progress

    Examples:
      | running state      | message             |
      | a scan is running  | scan cancelled.     |
      | no scan is running | no scan is running. |

  @id:editor-integrations.editor-scans.005 @rule:nvim.scans.disabled-plugin-never-scans @verified @source:extensions/nvim/lua/gandalf/scan.lua#may_start @test:extensions/nvim/tests/init_spec.lua#does nothing at all when the plugin is disabled
  Scenario: A disabled plugin never runs gandalf and shows no findings
    Given the plugin is set up with enabled = false
    When a workspace scan is requested
    Then no gandalf process is started
    And the status line reports no scan in progress
    And no gandalf diagnostics are shown in any buffer

  @id:editor-integrations.editor-scans.006 @rule:nvim.scans.file-scan-needs-project-file @inferred @source:extensions/nvim/plugin/gandalf.lua#GandalfScan
  Scenario: Scanning the current file is refused outside the project
    Given the current buffer has no file, or its file is outside the project root
    When the developer runs :GandalfScan
    Then a warning reads "Gandalf: open a file inside the project first."
    And no gandalf process is started
