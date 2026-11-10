@domain:reporting @area:ai-summary @from:gandalf/llm
Feature: Writing the AI summary of a run
  Gives the operator an LLM-written summary, change description, per-gate remediation and improvement ideas alongside the scorecard, without ever blocking the run when the model is unavailable.

  Background:
    Given the operator runs gandalf without --no-llm
    And the AI summary endpoint is set by GANDALF_LLM_URL and the model by GANDALF_MODEL

  @id:reporting.ai-summary.001 @rule:ai-summary.availability.degrades-to-note @inferred @source:src/gandalf/llm.py#analyze
  Scenario Outline: An unusable model leaves a one-line note instead of a summary
    Given GANDALF_LLM_URL is "http://llm.example.com:8787/v1" and GANDALF_MODEL is "gpt-oss-120b"
    And <problem>
    When the operator runs a check
    Then the summary reads "LLM unavailable (http://llm.example.com:8787/v1, model gpt-oss-120b): " followed by <reason>
    And the change description, remediation and improvement sections are empty
    And the gates still run and the scorecard and verdict are reported

    Examples:
      | problem                                        | reason                                                                      |
      | nothing is listening at the endpoint           | "no connection to llm.example.com:8787 within 10s" and the underlying error |
      | the endpoint refuses the request with HTTP 401 | the HTTP 401 error                                                          |
      | the model answers with no text at all          | "empty completion (finish_reason=length)"                                   |

  @id:reporting.ai-summary.002 @rule:ai-summary.availability.transient-failures-retried @verified @source:src/gandalf/llm.py#_request_with_retry @test:tests/test_llm.py#test_retries_then_succeeds @test:tests/test_llm.py#test_non_retryable_raises_immediately @test:tests/test_llm.py#test_exhausts_retries_and_raises @test:tests/test_llm.py#test_retryable_classification @test:tests/test_llm.py#test_connect_check_fails_fast_on_a_dead_endpoint @questionable
  Scenario Outline: Transient model failures are retried, a dead or refusing endpoint is not
    Given GANDALF_LLM_RETRIES is 2
    And the endpoint <behaviour>
    When the operator runs a check
    Then the model is asked <attempts> time(s)
    And the AI section shows <outcome>

    Examples:
      | behaviour                                      | attempts                              | outcome                    |
      | fails twice with a network error, then answers | 3                                     | the model's summary        |
      | fails every time with a network error          | 3                                     | the "LLM unavailable" note |
      | answers HTTP 503 every time                    | 3                                     | the "LLM unavailable" note |
      | answers HTTP 429 every time                    | 3                                     | the "LLM unavailable" note |
      | answers HTTP 400                               | 1                                     | the "LLM unavailable" note |
      | has nothing listening                          | 0, failing within the connect timeout | the "LLM unavailable" note |

  @id:reporting.ai-summary.003 @rule:ai-summary.endpoint.openai-compatible-request @inferred @source:src/gandalf/llm.py#chat
  Scenario: The summary is requested from an OpenAI-compatible chat completions endpoint
    Given GANDALF_LLM_URL is "http://llm.example.com:8787/v1/"
    And GANDALF_MODEL is "gpt-oss-120b", GANDALF_MAX_TOKENS is "8000" and GANDALF_API_KEY is "sk-test-example"
    When the operator runs a check
    Then gandalf POSTs JSON to "http://llm.example.com:8787/v1/chat/completions"
    And the request carries "Authorization: Bearer sk-test-example"
    And the body names model "gpt-oss-120b", max_tokens 8000 and a single user message
    And the text of the first choice's message is used, falling back to its reasoning text when the content is empty

  @id:reporting.ai-summary.004 @rule:ai-summary.privacy.context-is-bounded @inferred @source:src/gandalf/llm.py#repo_context
  Scenario: Only a bounded slice of the repository is sent to the model
    Given the repository has a 10,000-character README.md, 500 tracked files and a 20,000-character change under review
    When the operator runs a check
    Then the model receives the verdict and every gate's outcome and summary, with up to 15 findings for each gate that did not pass
    And it receives the first 2000 characters of the README, the first 200 tracked file paths and the last 5 commit subjects
    And it receives the first 6000 characters of the change, or no change section when nothing is in scope

  @id:reporting.ai-summary.005 @rule:ai-summary.sections.split-by-marker @inferred @source:src/gandalf/llm.py#_split_sections
  Scenario Outline: The model's reply is shown as summary, change, remediation and improvement sections
    Given the model's reply <reply>
    When the operator runs a check
    Then <result>

    Examples:
      | reply                                                                    | result                                                                   |
      | uses the four section markers, even wrapped in markdown bold or headings | each section shows the text under its own marker                         |
      | omits the improvement marker                                             | the improvement section is empty and the others show their text          |
      | ignores the marker format entirely                                       | the whole reply is shown as the summary and the other sections are empty |

  @id:reporting.ai-summary.006 @rule:ai-summary.remediation.placeholder-blocks-dropped @verified @source:src/gandalf/llm.py#_split_gates @test:tests/test_llm.py#test_split_gates_drops_already_addressed_stubs
  Scenario: Remediation is grouped per gate and placeholder blocks are left out
    Given the remediation section has a block for gate "grill_me" saying "- (Already addressed above.)"
    And it has a block for gate "mypy" saying "- src/gandalf/report.py:42 add a type hint for `f`"
    When the operator runs a check
    Then remediation is shown for gate "mypy"
    And no remediation block is shown for gate "grill_me"
