@domain:quality-gates @area:build-and-ci @from:gandalf/gates
Feature: Live-target, CI workflow and compliance checks
  Lets operators probe a running app, rehearse CI locally and check that a change delivers what was asked, without endangering third-party hosts.

  @id:quality-gates.build-and-ci.001 @rule:build-ci.dynamic.remote-target-needs-opt-in @inferred @source:src/gandalf/gates/dynamic.py#_guard
  Scenario Outline: Active scans against a non-local target are refused unless remote scanning is allowed
    Given the nikto, sqlmap and dalfox scanners are installed
    When the operator runs gandalf with --target <target><flag>
    Then the "nikto", "sqlmap" and "dalfox" gates <result>

    Examples:
      | target                      | flag            | result                                                                                                                 |
      | http://localhost:8080       |                 | scan the target                                                                                                        |
      | http://127.0.0.1:3000       |                 | scan the target                                                                                                        |
      | https://staging.example.com |                 | are reported as not checked, e.g. "nikto: refusing active scan against non-local target 'https://staging.example.com'" |
      | https://staging.example.com |  --allow-remote | scan the target                                                                                                        |

  @id:quality-gates.build-and-ci.002 @rule:build-ci.dynamic.no-target-not-checked @inferred @source:src/gandalf/gates/dynamic.py#_guard
  Scenario: Without a target URL the live scans are reported as not checked
    Given no live target is given
    When the operator runs gandalf
    Then the "nikto" gate is reported as not checked
    And its summary reads "nikto: no target URL — skipped (pass --target)"
    And the "sqlmap" and "dalfox" gates are reported as not checked the same way

  @id:quality-gates.build-and-ci.003 @rule:build-ci.dynamic.probes-fixed-api-path @inferred @source:src/gandalf/gates/dynamic.py#_endpoint @questionable
  Scenario: Injection and XSS probes always target the /api/v1/findings path of the target, without credentials
    Given a local app at http://localhost:8080 whose API is not under /api/v1
    When the operator runs gandalf with --target http://localhost:8080
    Then sqlmap probes http://localhost:8080/api/v1/findings?page=1&severity=high
    And dalfox probes http://localhost:8080/api/v1/findings?cluster=FUZZ&severity=FUZZ
    And no Authorization header is sent
    And the "sqlmap" and "dalfox" gates are green when those URLs reveal nothing

  @id:quality-gates.build-and-ci.004 @rule:build-ci.fuzz.crash-fails @verified @source:src/gandalf/gates/dynamic.py#AtherisGate @test:tests/test_gandalf.py#test_atheris_gate_ignores_its_own_artifact_prefix_flag
  Scenario Outline: A fuzzing crash turns the fuzz gate red, and a clean time-boxed run is green
    Given the repository has a fuzz harness at tests/fuzz/fuzz_adapters.py
    And atheris is installed
    When the operator runs gandalf
    Then the "atheris" gate is <colour>
    And its summary reads "<summary>"

    Examples:
      | fuzz run                                                   | colour | summary                            |
      | ends cleanly, its banner echoing the crash-artifact prefix | green  | atheris: 60s fuzz run — no crashes |
      | reports "ERROR: libFuzzer: deadly signal"                  | red    | atheris: crash detected in parser  |

  @id:quality-gates.build-and-ci.005 @rule:build-ci.act.local-workflow-run @inferred @source:src/gandalf/gates/ci_act.py#ActGate
  Scenario Outline: The repository's GitHub Actions workflows are run locally and their result sets the CI gate
    Given <situation>
    When the operator runs gandalf
    Then the "ci_act" gate is <result>
    And its summary reads "<summary>"

    Examples:
      | situation                                     | result                  | summary                                                       |
      | GANDALF_ACT is set to 0                       | green                   | act gate disabled (GANDALF_ACT=0)                             |
      | the repository has no .github/workflows/*.yml | green                   | no workflows to run                                           |
      | act is not installed                          | reported as not checked | 'act' not found; CI not verified locally                      |
      | Docker is not available                       | reported as not checked | Docker not available; act cannot run; CI not verified locally |
      | 2 workflows pass under act                    | green                   | act: 2 workflow(s) passed locally                             |
      | a workflow fails under act with exit 1        | red                     | act: workflow(s) failed locally (exit 1)                      |
      | act runs longer than the 900s default budget  | red                     | act timed out after 900s                                      |

  @id:quality-gates.build-and-ci.006 @rule:build-ci.compliance.meets-request @inferred @source:src/gandalf/gates/compliance.py#ComplianceGate
  Scenario Outline: The compliance judge passes a change that meets at least 85% of the request
    Given <request>
    When the operator runs gandalf
    Then the "compliance" gate is <result>
    And its summary reads "<summary>"

    Examples:
      | request                                                                                      | result                  | summary                                                    |
      | --title and --body describe the request and the judge rates the diff 92%                     | green                   | 92% compliant                                              |
      | --title and --body describe the request and the judge rates the diff 60% with 2 unmet points | red                     | 60% compliant · 2 unmet point(s)                           |
      | the judge returns a non-numeric compliance value                                             | red with score 0        | 0% compliant                                               |
      | no --title or --body is given                                                                | reported as not checked | compliance: no request/diff to judge (pass --title/--body) |

  @id:quality-gates.build-and-ci.007 @rule:build-ci.compliance.judge-unreachable-red @inferred @source:src/gandalf/gates/compliance.py#ComplianceGate @questionable
  Scenario: An unreachable compliance judge turns the gate red instead of reporting it as not checked
    Given --title and --body describe the request
    And the LLM endpoint refuses connections
    When the operator runs gandalf
    Then the "compliance" gate is red with score 0
    And its summary reads "compliance: judge unavailable (connection refused)"
