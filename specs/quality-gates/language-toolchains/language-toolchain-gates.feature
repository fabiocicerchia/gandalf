@domain:quality-gates @area:language-toolchains @from:gandalf/gates
Feature: Checking each language's build, lint and tests
  Lets polyglot teams get a build, lint and test verdict for every ecosystem in the repository without being penalised for languages they do not use.

  @id:quality-gates.language-toolchains.001 @rule:toolchains.ecosystem.absent-is-green-skip @verified @source:src/gandalf/gates/_toolchain.py#ToolchainGate @test:tests/test_lang_gates.py#test_absent_ecosystem_is_a_green_skip
  Scenario Outline: A language the repository does not use is a green skip
    Given a Python-only repository
    When the operator runs gandalf
    Then the "<gate>" gate is green with score 1.0
    And its summary reads "<summary>"

    Examples:
      | gate         | summary                                                                   |
      | java_build   | java: not in this tree (no pom.xml, build.gradle, build.gradle.kts)       |
      | dotnet_build | dotnet: not in this tree (no *.sln, *.slnx, *.csproj, *.fsproj, *.vbproj) |
      | cpp_build    | cmake: not in this tree (no CMakeLists.txt)                               |
      | go_build     | go: no module (no go.mod)                                                 |
      | cargo_build  | rust: no crate (no Cargo.toml)                                            |
      | eslint       | node: no package.json                                                     |

  @id:quality-gates.language-toolchains.002 @rule:toolchains.ecosystem.missing-toolchain-named @verified @source:src/gandalf/gates/_toolchain.py#ToolchainGate @test:tests/test_lang_gates.py#test_missing_toolchain_warns_and_names_the_binary
  Scenario Outline: A language that is present but whose toolchain is not installed is reported as not checked, naming the binary
    Given a repository containing <marker>
    And <binary> is not installed
    When the operator runs gandalf
    Then the "<gate>" gate is reported as not checked
    And its summary reads "<binary> not installed — skipped"

    Examples:
      | gate           | marker         | binary   |
      | java_build     | pom.xml        | mvn      |
      | ktlint         | A.kt           | ktlint   |
      | rubocop        | Gemfile        | rubocop  |
      | composer_audit | composer.lock  | composer |
      | cppcheck       | a.cpp          | cppcheck |
      | dotnet_build   | App/App.csproj | dotnet   |
      | go_build       | go.mod         | go       |
      | cargo_build    | Cargo.toml     | cargo    |

  @id:quality-gates.language-toolchains.003 @rule:toolchains.blocking.build-and-syntax-only @verified @source:src/gandalf/gates/cpp.py#CppBuildGate @test:tests/test_lang_gates.py#test_only_the_build_and_syntax_gates_are_blocking @test:tests/test_lang_gates.py#test_cpp_build_is_advisory @test:tests/test_gandalf.py#test_discovery_finds_builtins
  Scenario Outline: Only build and syntax gates are marked blocking; C/C++ build is advisory
    Given the "<gate>" gate applies to the repository
    When the operator runs gandalf
    Then the scorecard <marking> the "<gate>" gate as blocking

    Examples:
      | gate          | marking       |
      | build         | marks         |
      | go_build      | marks         |
      | cargo_build   | marks         |
      | java_build    | marks         |
      | ruby_syntax   | marks         |
      | php_syntax    | marks         |
      | dotnet_build  | marks         |
      | cpp_build     | does not mark |
      | ruff          | does not mark |
      | java_test     | does not mark |
      | dotnet_format | does not mark |

  @id:quality-gates.language-toolchains.004 @rule:toolchains.ruby.stray-config-not-a-project @verified @source:src/gandalf/gates/ruby.py#RubocopGate @test:tests/test_lang_gates.py#test_a_stray_ruby_config_does_not_make_a_ruby_project
  Scenario: A stray Ruby config file gets a syntax check but not Ruby lint, audit or tests
    Given a Python repository whose only Ruby file is the markdown-lint config .mdl_style.rb
    When the operator runs gandalf
    Then the "rubocop", "ruby_test" and "bundler_audit" gates are green with a "not in this tree" summary

  @id:quality-gates.language-toolchains.005 @rule:toolchains.syntax.unparseable-file-fails @verified @source:src/gandalf/gates/_toolchain.py#per_file @test:tests/test_lang_gates.py#test_ruby_syntax_reads_real_ruby
  Scenario Outline: A source file that does not parse turns the syntax gate red and names the file
    Given the change includes <file>, which does not parse
    When the operator runs gandalf
    Then the "<gate>" gate is red with score 0
    And its summary names <file> as the first file that does not parse
    And a finding points at <file>

    Examples:
      | gate        | file          |
      | ruby_syntax | lib/a.rb      |
      | php_syntax  | src/index.php |
      | build       | app/main.py   |

  @id:quality-gates.language-toolchains.006 @rule:toolchains.cpp.configure-failure-not-red @verified @source:src/gandalf/gates/cpp.py#CppBuildGate @test:tests/test_lang_gates.py#test_cpp_build_compiles_and_fails_honestly
  Scenario Outline: A C/C++ project that cannot be configured is reported as not checked, while a compile error is red
    Given a CMake project where <situation>
    When the operator runs gandalf
    Then the "cpp_build" gate is <result>
    And its summary begins "<summary>"

    Examples:
      | situation                                              | result                  | summary                                     |
      | a required system library is missing at configure time | reported as not checked | cmake: configure failed (toolchain or deps) |
      | main.cpp has a compile error                           | red with score 0        | cmake: does not compile                     |
      | everything compiles                                    | green                   | cmake: compiles                             |

  @id:quality-gates.language-toolchains.007 @rule:toolchains.lint.count-thresholds @verified @source:src/gandalf/gates/_toolchain.py#counted @test:tests/test_lang_gates.py#test_counted_scoring_matches_the_house_rules
  Scenario Outline: Lint and type-check findings turn a gate amber, then red past its limit
    Given the "<gate>" tool reports <findings>
    When the operator runs gandalf
    Then the "<gate>" gate is <colour>

    Examples:
      | gate          | findings                 | colour |
      | rubocop       | no offences              | green  |
      | rubocop       | 3 offences               | amber  |
      | rubocop       | 4 offences               | red    |
      | ruff          | 3 findings               | amber  |
      | ruff          | 4 findings               | red    |
      | golangci_lint | 4 issues                 | red    |
      | clippy        | 4 diagnostics            | red    |
      | mypy          | 10 type errors           | amber  |
      | mypy          | 11 type errors           | red    |
      | tsc           | 10 type errors           | amber  |
      | tsc           | 11 type errors           | red    |
      | eslint        | 5 warnings and no errors | amber  |
      | eslint        | 1 error                  | red    |

  @id:quality-gates.language-toolchains.008 @rule:toolchains.python-tests.no-signal-not-red @verified @source:src/gandalf/gates/supply_chain.py#TestsGate @test:tests/test_tests_gate.py#test_missing_pytest_is_amber_not_red @test:tests/test_lang_gates.py#test_python_tests_gate_skips_a_tree_with_no_tests
  Scenario Outline: A Python test suite that cannot run is reported as not checked, while failing tests are red
    Given a Python repository configured for pytest where <situation>
    When the operator runs gandalf
    Then the "tests" gate is <result>
    And its summary begins "<summary>"

    Examples:
      | situation                                                   | result                  | summary                               |
      | pytest is installed neither for the interpreter nor on PATH | reported as not checked | tests: pytest not installed — skipped |
      | pytest collects no tests                                    | reported as not checked | tests: no tests collected — skipped   |
      | 2 tests fail                                                | red with score 0.8      | tests: 2 failure(s)                   |
      | the suite runs longer than 120 seconds                      | red with score 0        | tests: timed out after 120s           |
      | every test passes                                           | green                   | tests: passed                         |
