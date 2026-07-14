# Review Checklist (82 items)

The full checklist behind the gates, condensed from
https://github.com/fabiocicerchia/code-challenge-review-checklist — every original category is
folded into exactly one gate, no duplication. Use this file two ways:

1. **As scoring evidence** — when scoring a gate in `rubric.md`, work through that gate's items.
2. **As a printable checklist** — only when the user asks ("show the full checklist", "tick the
   boxes", "item by item"), render the items below grouped by gate, marking each **✓** (met),
   **✗** (not met — add a one-line note), or **N/A** (cannot apply to this artifact).

## Applicability (N/A) rules

- **Bare diff / PR** (changed lines only): mark repo-level items N/A — README, Usage, CLI help,
  UML, all of Environment, all of Versioning, Language/EOL, Folder structure, i18n, Presentation.
  Gate 6 is usually entirely N/A and dropped from the score.
- **Full repo / code-challenge submission**: all items apply.
- Mark anything you genuinely cannot verify (no CI, can't run the linter) as unverified in NOTES
  rather than guessing ✓/✗.

## Language-tool mapping

Detect the primary language from extensions and config files, then read the generic items
("linter clean", "formatter clean", "doc-comments", "package manager") against that ecosystem:

| Language | Linter | Formatter | Doc-comments | Package manager |
|----------|--------|-----------|--------------|-----------------|
| PHP | phpcbf / PHP_CodeSniffer | php-cs-fixer | DocBlocks | Composer |
| JS / TS | ESLint | Prettier | JSDoc / TSDoc | npm / pnpm / yarn |
| Python | Ruff / flake8 / pylint | Black / ruff format | docstrings | pip / Poetry / uv |
| Go | go vet / golangci-lint | gofmt | godoc | Go modules |
| Java | Checkstyle / SpotBugs | google-java-format | Javadoc | Maven / Gradle |
| Ruby | RuboCop | rubocop -a | YARD | Bundler |
| Rust | Clippy | rustfmt | rustdoc | Cargo |

If the language isn't in the table, substitute its standard equivalents and note which you used.

---

## Gate 1 — Correctness & algorithm
**Algorithm**
- [ ] Big-O analysed and appropriate
- [ ] Recursive approach used appropriately (no needless/unbounded recursion)
- [ ] Covers edge cases
- [ ] Example provided matches actual output
- [ ] Return values match the expected type/contract

**Performance**
- [ ] Speed is acceptable for the input sizes
- [ ] Number of loops minimised (no needless passes / quadratic blow-up)

## Gate 2 — Tests & CI
**Tests**
- [ ] Unit tests present and meaningful
- [ ] Functional / integration tests where the change spans components
- [ ] Coverage > 80% of the changed code
- [ ] CI/CD configured and green

## Gate 3 — Security & robustness
**Security**
- [ ] No buffer overflow / unbounded buffer handling
- [ ] No freezing (infinite loop, runaway recursion, memory leaks)
- [ ] No stacktraces / internals leaked to users
- [ ] Immutable variables where state shouldn't change
- [ ] Exceptions caught and handled (not swallowed)
- [ ] Resources closed (files, streams, connections, locks)
- [ ] Input validation on untrusted data
- [ ] No deprecated APIs
- [ ] No warnings left
- [ ] No `eval` / unsafe dynamic execution

## Gate 4 — Clean code & design
**Clean Code**
- [ ] Production ready
- [ ] No dead code
- [ ] No commented-out code
- [ ] Namespace usage correct
- [ ] No global variables
- [ ] Correct visibility modifiers
- [ ] No duplicated code
- [ ] No empty blocks
- [ ] Correct data types / structures
- [ ] Design patterns used sensibly
- [ ] No mixed tabs vs spaces
- [ ] No gratuitous getters & setters
- [ ] Use exceptions rather than return codes
- [ ] Don't return null (prefer empty/optional)
- [ ] Class made final if not used for inheritance
- [ ] Dependency injection over hidden construction
- [ ] No dependency cycles

**Complexity**
- [ ] No overly complex expressions
- [ ] No obscure bitwise operations
- [ ] No magic variables
- [ ] No magic values
- [ ] No magic methods
- [ ] Law of Demeter respected
- [ ] Not over-engineered

**Paradigms**
- [ ] DRY
- [ ] GRASP
- [ ] Not quick & dirty
- [ ] SOLID
- [ ] Coherent OOP

**Coding Style**
- [ ] Code linted clean
- [ ] Respects community standards
- [ ] No linter issues (e.g. phpcbf)
- [ ] No formatter issues (e.g. php-cs-fixer)
- [ ] Sane folder structure
- [ ] No debug code

## Gate 5 — Readability & documentation
**Readability**
- [ ] Clear variable names
- [ ] Correct spelling
- [ ] No double negations
- [ ] No deep nesting (if/for/while)

**Documentation**
- [ ] Doc-comments on public APIs (e.g. DocBlocks)
- [ ] README file
- [ ] Usage instructions
- [ ] Code is readable
- [ ] CLI help where there's a CLI
- [ ] No TODOs
- [ ] No HACKs
- [ ] Logs where appropriate
- [ ] Unusual behaviour is commented
- [ ] UML / diagram where design is non-trivial

## Gate 6 — Project & delivery hygiene
**Environment**
- [ ] Dockerized
- [ ] docker-compose
- [ ] .env file / example

**Versioning**
- [ ] Git repo
- [ ] Many small commits
- [ ] Good commit messages
- [ ] .gitignore

**Language**
- [ ] Package manager declared
- [ ] Version within EOL
- [ ] Using a reasonably recent version

**i18n**
- [ ] Translations / externalised strings where text is user-facing

**Presentation**
- [ ] Coloured / clear shell output where there's CLI output
