@domain:running-checks @area:configuration @from:gandalf/config
Feature: Configuring a run from the repository
  Lets a team keep gandalf's gate selection and tuning in a version-controlled .gandalf.toml so every run of the repo, local or CI, checks the same things.

  Background:
    Given a repository with gates "ruff", "mypy" and "gitleaks" available

  @id:running-checks.configuration.002 @rule:config.location.precedence @verified @source:src/gandalf/config.py#load @test:tests/test_config.py#test_explicit_and_env_paths @test:tests/test_config.py#test_load_and_sections
  Scenario Outline: The config file is taken from --config, then GANDALF_CONFIG, then the repository root
    Given the repository root has a .gandalf.toml that skips "mypy"
    And <other> is a config file that skips "gitleaks"
    When the operator runs gandalf <how>
    Then the gate "<skipped>" is reported as disabled
    And the gate "<run>" is run

    Examples:
      | other          | how                                       | skipped  | run      |
      | ci/strict.toml | with --config ci/strict.toml              | gitleaks | mypy     |
      | ci/strict.toml | with GANDALF_CONFIG set to ci/strict.toml | gitleaks | mypy     |
      | (none)         | with no config option                     | mypy     | gitleaks |

  @id:running-checks.configuration.003 @rule:config.load.broken-file-falls-back-to-defaults @verified @source:src/gandalf/config.py#load @test:tests/test_config.py#test_broken_config_falls_back
  Scenario: An unreadable or malformed config is ignored with a warning and the run continues on defaults
    Given the repository's .gandalf.toml is not valid TOML
    When the operator runs gandalf on the repository
    Then gandalf warns "gandalf: ignoring config" followed by the file path and the parse error
    And every gate runs as if there were no config

  @id:running-checks.configuration.004 @rule:config.location.missing-named-file-silently-ignored @inferred @source:src/gandalf/config.py#load @questionable
  Scenario Outline: A named config file that does not exist is silently ignored, even when the repository has its own
    Given the repository root has a .gandalf.toml that skips "mypy"
    And no file exists at ci/missing.toml
    When the operator runs gandalf <how>
    Then no warning about the config is printed
    And the gate "mypy" is run
    And no gate is reported as disabled by config

    Examples:
      | how                                        |
      | with --config ci/missing.toml              |
      | with GANDALF_CONFIG set to ci/missing.toml |
