@domain:gate-extensibility @area:plugin-api @from:gandalf/plugins
Feature: Adding custom gates
  Lets operators and gate authors add their own gates, or swap a built-in scanner, without editing gandalf, while never letting a replacement pass silently.

  Background:
    Given gandalf ships its built-in gates

  @id:gate-extensibility.plugin-api.001 @rule:plugins.discovery.custom-gate-dirs-loaded @verified @source:src/gandalf/plugins.py#discover_gates @test:tests/test_gates_path.py#test_a_new_gate_is_not_announced
  Scenario: A gate dropped into a directory on GANDALF_GATES_PATH runs alongside the built-in gates
    Given a directory /opt/acme-gates containing a gate file that defines a gate named "acme_licence_header"
    And GANDALF_GATES_PATH is set to "/opt/acme-gates"
    When the operator runs gandalf
    Then the gate "acme_licence_header" is part of the run
    And every built-in gate is still part of the run
    And no override warning is printed

  @id:gate-extensibility.plugin-api.002 @rule:plugins.discovery.override-announced @verified @source:src/gandalf/plugins.py#discover_gates @test:tests/test_gates_path.py#test_overriding_a_builtin_is_announced
  Scenario: A custom gate that takes a built-in gate's name replaces it and the operator is warned
    Given a directory /opt/acme-gates containing a gate file /opt/acme-gates/plug.py that defines a gate named "gitleaks"
    And GANDALF_GATES_PATH is set to "/opt/acme-gates"
    When the operator runs gandalf
    Then the "gitleaks" result comes from the custom gate, not the built-in scanner
    And stderr shows "gandalf: gate 'gitleaks' overridden by /opt/acme-gates/plug.py (GANDALF_GATES_PATH)"
    And the run continues

  @id:gate-extensibility.plugin-api.003 @rule:plugins.discovery.builtins-load-silently @verified @source:src/gandalf/plugins.py#discover_gates @test:tests/test_gates_path.py#test_builtin_gates_never_warn_about_each_other @test:tests/test_gandalf.py#test_discovery_finds_builtins
  Scenario: With no custom gate directories, the built-in gates load without any warning
    Given GANDALF_GATES_PATH is not set
    When the operator runs gandalf
    Then built-in gates such as "ruff", "semgrep", "bandit" and "gitleaks" are part of the run
    And nothing about gate loading is printed to stderr

  @id:gate-extensibility.plugin-api.004 @rule:plugins.discovery.underscore-files-not-gates @inferred @source:src/gandalf/plugins.py#discover_gates
  Scenario: Gate files whose names start with an underscore are never loaded as gates
    Given a directory /opt/acme-gates containing "_shared.py" that defines a gate-shaped class named "acme_base"
    And GANDALF_GATES_PATH is set to "/opt/acme-gates"
    When the operator runs gandalf
    Then no gate named "acme_base" is part of the run

  @id:gate-extensibility.plugin-api.005 @rule:plugins.discovery.missing-dirs-ignored @inferred @source:src/gandalf/plugins.py#_gate_dirs @questionable
  Scenario: A directory on GANDALF_GATES_PATH that does not exist is ignored without a warning
    Given GANDALF_GATES_PATH is set to "/opt/acme-gatez" and that directory does not exist
    When the operator runs gandalf
    Then only the built-in gates are part of the run
    And no warning about the missing directory is printed
