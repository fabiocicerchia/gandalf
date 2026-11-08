@domain:quality-gates @area:supply-chain @from:gandalf/gates
Feature: Judging dependencies, licences and repository posture
  Tells operators whether a change brings in vulnerable packages, licences with obligations or weak security practices.

  Background:
    Given the scanner each gate needs is installed on the host or in the gandalf-tools image

  @id:quality-gates.supply-chain.001 @rule:supply-chain.vulnerabilities.thresholds @verified @source:src/gandalf/gates/supply_chain.py#OsvGate @test:tests/test_shared_scan.py#test_both_gates_read_one_scan
  Scenario Outline: Known vulnerable dependencies turn the matching gate amber or red
    Given the "<gate>" scanner reports <findings>
    When the operator runs gandalf
    Then the "<gate>" gate is <colour>
    And its summary reads "<summary>"

    Examples:
      | gate           | findings                           | colour | summary                                                     |
      | osv            | 2 vulnerable Python packages       | amber  | osv: 2 vulnerability(ies)                                   |
      | osv            | 3 vulnerable Python packages       | red    | osv: 3 vulnerability(ies)                                   |
      | osv_scanner    | 3 vulnerabilities                  | red    | osv-scanner: 3 vulnerability(ies)                           |
      | cargo_audit    | 1 RUSTSEC advisory                 | red    | cargo-audit: 1 vulnerability(ies)                           |
      | govulncheck    | 1 reachable vulnerability          | red    | govulncheck: 1 vulnerability(ies)                           |
      | composer_audit | 1 Packagist advisory               | red    | composer audit: 1 advisory(ies)                             |
      | bundler_audit  | 1 vulnerable gem                   | red    | bundler-audit: 1 vulnerable gem(s)                          |
      | dotnet_audit   | 1 vulnerable NuGet package         | red    | dotnet audit: 1 vulnerable package(s)                       |
      | trivy          | 1 secret and nothing else          | red    | trivy: 0 vuln(s), 1 secret(s), 0 misconfig(s), 0 license(s) |
      | trivy          | 4 vulnerabilities and nothing else | amber  | trivy: 4 vuln(s), 0 secret(s), 0 misconfig(s), 0 license(s) |
      | trivy          | 5 vulnerabilities and nothing else | red    | trivy: 5 vuln(s), 0 secret(s), 0 misconfig(s), 0 license(s) |

  @id:quality-gates.supply-chain.002 @rule:supply-chain.licenses.only-obligations-flagged @verified @source:src/gandalf/gates/licenses.py#LicensesGate @test:tests/test_shared_scan.py#test_both_gates_read_one_scan
  Scenario Outline: Only licences that carry obligations are flagged, and forbidden ones turn the gate red
    Given the repository's dependencies carry licences rated <ratings>
    When the operator runs gandalf
    Then the "licenses" gate is <colour>
    And its summary reads "<summary>"

    Examples:
      | ratings              | colour | summary                                      |
      | LOW and UNKNOWN only | green  | licenses: no problematic licenses            |
      | one MEDIUM           | amber  | licenses: 1 flagged (0 forbidden/restricted) |
      | one HIGH (GPL-3.0)   | red    | licenses: 1 flagged (1 forbidden/restricted) |

  @id:quality-gates.supply-chain.003 @rule:supply-chain.trivy.permissive-licences-lower-score @inferred @source:src/gandalf/gates/supply_chain.py#TrivyGate @questionable
  Scenario: Permissive licences lower the trivy gate's score even though the licences gate ignores them
    Given trivy reports 10 LOW-rated licences and nothing else
    When the operator runs gandalf
    Then the "trivy" gate is amber with score 0
    And its summary reads "trivy: 0 vuln(s), 0 secret(s), 0 misconfig(s), 10 license(s)"
    And the "licenses" gate is green

  @id:quality-gates.supply-chain.004 @rule:supply-chain.scorecard.posture-bands @inferred @source:src/gandalf/gates/scorecard.py#ScorecardGate
  Scenario Outline: The OSSF Scorecard aggregate sets the posture gate's colour
    Given OSSF Scorecard in local mode rates the repository <aggregate>/10
    When the operator runs gandalf
    Then the "scorecard" gate is <colour>
    And each check scoring below 10 is listed with its reason

    Examples:
      | aggregate                     | colour                                                                             |
      | 8.2                           | green                                                                              |
      | 7.0                           | green                                                                              |
      | 5.0                           | amber                                                                              |
      | 3.1                           | red                                                                                |
      | -1 (every check inconclusive) | not checked, with summary "scorecard: no conclusive checks (local mode) — skipped" |

  @id:quality-gates.supply-chain.005 @rule:supply-chain.iac.checkov-share-passed @inferred @source:src/gandalf/gates/supply_chain.py#CheckovGate
  Scenario Outline: Checkov scores by the share of checks passed and turns red at five failures
    Given checkov runs 40 infrastructure checks and <failed> of them fail
    When the operator runs gandalf
    Then the "checkov" gate is <colour> with score <score>
    And its summary reads "<summary>"

    Examples:
      | failed | colour | score | summary                       |
      | 0      | green  | 1.0   | checkov: 40 check(s) passed   |
      | 2      | amber  | 0.95  | checkov: 2 failed / 40 checks |
      | 5      | red    | 0.875 | checkov: 5 failed / 40 checks |
