# Gandalf — feature backlog

Missing capabilities for the quality-gate evaluator, split into **must-have**
(needed before gandalf is a dependable CI gate on real repos) and
**nice-to-have** (raises the bar once the core is solid). Grounded in the
current code.

Shipped items are removed as they land; the record of what was built, with the
file each capability lives in, is in this file's git history.

---

## Must-have

Nothing open.

---

## Nice-to-have

- [ ] **More language suites.** Rust done (`gandalf/gates/rust.py`:
  `cargo build`/`clippy`/`cargo-audit`/`cargo test`, tagged `langs={"rust"}`).
  Java/Kotlin, Ruby, PHP, C/C++, .NET still open — same pattern, one gate file
  per language, see `rust.py`/`golang.py` as the template.
