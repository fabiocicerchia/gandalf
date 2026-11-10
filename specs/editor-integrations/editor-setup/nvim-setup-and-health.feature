@domain:editor-integrations @area:editor-setup @from:extensions/nvim
Feature: Configuring and checking the Neovim plugin
  Lets a Neovim user configure the plugin safely and find out why scans produce nothing, before a scan fails a minute in.

  Background:
    Given the gandalf Neovim plugin is installed

  @id:editor-integrations.editor-setup.001 @rule:nvim.setup.invalid-settings-rejected @verified @source:extensions/nvim/lua/gandalf/config.lua#M.validate @test:extensions/nvim/tests/config_spec.lua#rejects an empty cmd @test:extensions/nvim/tests/config_spec.lua#never scans on a keystroke @test:extensions/nvim/tests/config_spec.lua#rejects a trigger it does not have @test:extensions/nvim/tests/config_spec.lua#rejects a debounce too short to collapse a burst of saves @test:extensions/nvim/tests/config_spec.lua#rejects a level that is not on the ladder @test:extensions/nvim/tests/config_spec.lua#rejects a non-boolean scan.debug, which would silently never log
  Scenario Outline: Invalid settings are rejected when the plugin is set up
    Given the developer configures <setting>
    When the plugin is set up
    Then setup fails with an error naming <field>

    Examples:
      | setting                                | field                 |
      | cmd = {}                               | cmd                   |
      | scan.trigger = "on_type"               | scan.trigger          |
      | scan.debounce_ms = 10                  | scan.debounce_ms      |
      | diagnostics.min_level = "catastrophic" | diagnostics.min_level |
      | scan.debug = "yes"                     | scan.debug            |

  @id:editor-integrations.editor-setup.002 @rule:nvim.setup.commands-work-without-setup @verified @source:extensions/nvim/plugin/gandalf.lua#ready @test:extensions/nvim/tests/config_spec.lua#resolves without options
  Scenario: Commands work with the default settings when setup was never called
    Given the developer has not called setup
    When the developer runs any :Gandalf command
    Then the plugin sets itself up with the default settings first
    And the command runs against the gandalf command "gandalf" with trigger on_save

  @id:editor-integrations.editor-setup.003 @rule:nvim.health.gandalf-command @verified @source:extensions/nvim/lua/gandalf/health.lua#check_command @test:extensions/nvim/tests/health_spec.lua#says how to fix it when the command is not executable @test:extensions/nvim/tests/health_spec.lua#does not take any runnable command for gandalf @test:extensions/nvim/tests/health_spec.lua#accepts a build that identifies itself, and reports what it can stream @test:extensions/nvim/tests/health_spec.lua#warns that findings will only arrive at the end when the build has no --stream
  Scenario Outline: The health check says whether the configured command is a working gandalf
    Given the configured command <command>
    When the developer runs :checkhealth gandalf
    Then it reports <result>

    Examples:
      | command                                      | result                                                                                                                   |
      | is not executable                            | an error "`<cmd>` is not executable" with advice to run make install or point cmd at a checkout with PYTHONPATH          |
      | runs but its --help does not mention gandalf | a warning "`<cmd>` ran, but does not look like gandalf"                                                                  |
      | is gandalf with --stream                     | "`<cmd>` runs" and "this build supports --stream, so findings appear during a scan"                                      |
      | is gandalf without --stream                  | "`<cmd>` runs" and a warning "this build has no --stream support": findings will only appear when the whole run finishes |

  @id:editor-integrations.editor-setup.004 @rule:nvim.health.environment @verified @source:extensions/nvim/lua/gandalf/health.lua#M.check @test:extensions/nvim/tests/health_spec.lua#names the project root it resolved, because that is what gandalf will scan @test:extensions/nvim/tests/health_spec.lua#confirms a git repository, since gandalf resolves its scope from one @questionable
  Scenario Outline: The health check reports the repository, the scanner image and the LLM endpoint
    Given <environment>
    When the developer runs :checkhealth gandalf
    Then it reports <result>

    Examples:
      | environment                                                  | result                                                                    |
      | the project root has a .git directory                        | "project root: <root>" and "git repository"                               |
      | the project root is not a git repository                     | a warning that there is nothing to scan                                   |
      | docker is not installed                                      | a warning that gates whose tool is missing will report it unavailable     |
      | docker has no gandalf-tools image                            | a warning "scanner tools: \"gandalf-tools\" missing" advising make tools  |
      | the LLM endpoint at http://127.0.0.1:8787/v1 does not answer | information that the judge gates will skip and everything else still runs |
