@domain:quality-gates @area:security-scanning @from:gandalf/gates
Feature: Catching leaked secrets and security flaws
  Gives operators a red or amber signal when a change leaks a credential or adds a security flaw, so it can be stopped before merge.

  Background:
    Given the scanner each gate needs is installed on the host or in the gandalf-tools image

  @id:quality-gates.security-scanning.001 @rule:security.secrets.leaked-secret-blocks-run @verified @source:src/gandalf/gates/secrets.py#GitleaksGate @test:tests/test_gandalf.py#test_discovery_finds_builtins
  Scenario: A detected secret turns the run red as a blocking gate
    Given a repository whose history contains 2 committed credentials
    When the operator runs gandalf
    Then the "gitleaks" gate is red with score 0
    And its summary reads "gitleaks: 2 potential secret(s) detected"
    And the scorecard marks the "gitleaks" gate as blocking
    And the secret values in its findings are redacted

  @id:quality-gates.security-scanning.002 @rule:security.secrets.unreadable-scan-reads-clean @inferred @source:src/gandalf/gates/secrets.py#GitleaksGate @questionable
  Scenario: Secret-scanner output that cannot be read is reported as no secrets found
    Given the secret scanner prints an error message instead of its JSON report
    When the operator runs gandalf
    Then the "gitleaks" gate is green with score 1.0
    And its summary reads "gitleaks: no secrets found"

  @id:quality-gates.security-scanning.003 @rule:security.sast.severity-sets-verdict @verified @source:src/gandalf/gates/semgrep.py#SemgrepGate @test:tests/test_kics.py#test_all_encrypted_leaves_only_real_findings
  Scenario Outline: Static-analysis findings turn a gate red by severity or volume, amber otherwise
    Given the "<gate>" scanner reports <findings> on the change
    When the operator runs gandalf
    Then the "<gate>" gate is <colour>
    And its summary reads "<summary>"

    Examples:
      | gate    | findings                      | colour | summary                                        |
      | bandit  | 1 HIGH-severity issue         | red    | bandit: 1 issue(s), 1 HIGH                     |
      | bandit  | 2 LOW-severity issues         | amber  | bandit: 2 issue(s), 0 HIGH                     |
      | semgrep | 1 ERROR-severity finding      | red    | semgrep: 1 finding(s)                          |
      | semgrep | 6 WARNING-severity findings   | red    | semgrep: 6 finding(s)                          |
      | semgrep | 2 WARNING-severity findings   | amber  | semgrep: 2 finding(s)                          |
      | codeql  | 1 error-level Python alert    | red    | codeql (python): 1 error, 0 warning finding(s) |
      | codeql  | 3 warning-level Python alerts | amber  | codeql (python): 0 error, 3 warning finding(s) |
      | kics    | 1 HIGH misconfiguration       | red    | kics: 1 HIGH, 0 MEDIUM, 0 LOW                  |
      | kics    | 1 MEDIUM misconfiguration     | amber  | kics: 0 HIGH, 1 MEDIUM, 0 LOW                  |

  @id:quality-gates.security-scanning.004 @rule:security.iac.sops-encrypted-values-not-secrets @verified @source:src/gandalf/gates/kics.py#_drop_encrypted @test:tests/test_kics.py#test_encrypted_secret_dropped_plain_one_kept @test:tests/test_kics.py#test_all_encrypted_leaves_only_real_findings @test:tests/test_kics.py#test_unreadable_file_keeps_the_finding
  Scenario: SOPS-encrypted values are not reported as leaked passwords, plain values still are
    Given a Kubernetes secret file k8s/app.sops.yaml with one SOPS-encrypted password and one plain-text password
    And a Dockerfile with one MEDIUM misconfiguration
    When the operator runs gandalf
    Then the "kics" gate reports the plain-text password on line 5 as a finding
    And it does not report the encrypted password
    And its summary reads "kics: 1 HIGH, 1 MEDIUM, 0 LOW"
    And when every password in the file is encrypted the "kics" gate is amber with summary "kics: 0 HIGH, 1 MEDIUM, 0 LOW"

  @id:quality-gates.security-scanning.005 @rule:security.sast.codeql-analyses-detected-languages @verified @source:src/gandalf/gates/codeql.py#_codeql_langs @test:tests/test_lang_gates.py#test_codeql_whole_tree_analyzes_only_detected_languages
  Scenario Outline: CodeQL analyses only the languages present in scope
    Given a whole-tree run where gandalf detected the languages <detected>
    When the operator runs gandalf
    Then the "codeql" gate analyses <analysed>

    Examples:
      | detected         | analysed                                                                             |
      | python and shell | python only                                                                          |
      | go, ts and node  | go and javascript                                                                    |
      | shell only       | nothing, and the gate is green with summary "codeql: no supported language in scope" |
      | nothing known    | go, javascript and python                                                            |
