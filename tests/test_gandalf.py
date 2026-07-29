"""Runnable checks for the non-trivial logic: RAG aggregation + plugin discovery.
Run: pytest gandalf/test_gandalf.py   (or: python gandalf/test_gandalf.py)
"""

from __future__ import annotations

import asyncio

from gandalf import llm, skillgate, skills
from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import discover_gates
from gandalf.report import _CATEGORY, _GROUP_ORDER, aggregate
from gandalf.scope import _classify

P = GateOutcome.PASS
W = GateOutcome.WARN
F = GateOutcome.FAIL


def _r(outcome, score):
    return GateResult("x", outcome, score)


def test_aggregate_rag():
    assert aggregate([_r(P, 1.0), _r(P, 1.0)]).outcome is P  # all pass → green
    assert aggregate([_r(P, 1.0), _r(W, 0.8)]).outcome is W  # any warn → amber
    assert aggregate([_r(P, 1.0), _r(F, 0.0)]).outcome is F  # any fail → red
    assert aggregate([_r(W, 0.8), _r(F, 0.0)]).outcome is F  # fail beats warn
    assert aggregate([]).outcome is W  # nothing ran → amber


def test_aggregate_score():
    assert aggregate([_r(P, 1.0), _r(P, 0.0)]).score == 50
    assert aggregate([_r(P, 1.0)]).score == 100


def test_discovery_finds_builtins():
    names = {g.name for g in discover_gates()}
    expected = {
        # python
        "build",
        "ruff",
        "semgrep",
        "codeql",
        "bandit",
        "gitleaks",
        "mypy",
        "vulture",
        "format",
        # supply-chain / iac
        "osv",
        "osv_scanner",
        "trivy",
        "checkov",
        "kics",
        "hadolint",
        "scorecard",
        "tests",
        # database
        "sqlfluff",
        "squawk",
        # licensing / docs / complexity
        "licenses",
        "interrogate",
        "lizard",
        # polyglot lint
        "shellcheck",
        "actionlint",
        "yamllint",
        "codespell",
        "mdl",
        # go
        "go_build",
        "golangci_lint",
        "govulncheck",
        "go_test",
        # rust
        "cargo_build",
        "clippy",
        "cargo_audit",
        "cargo_test",
        # node
        "eslint",
        "tsc",
        "node_test",
        # ci / compliance / dynamic
        "ci_act",
        "compliance",
        "atheris",
        "nikto",
        "sqlmap",
        "dalfox",
    }
    assert expected <= names, f"missing: {expected - names}"
    # blocking gates: build (py) + go_build + gitleaks
    by_name = {g.name: g for g in discover_gates()}
    assert by_name["build"].blocking is True
    assert by_name["go_build"].blocking is True
    assert by_name["cargo_build"].blocking is True
    assert by_name["gitleaks"].blocking is True
    assert by_name["ruff"].blocking is False


def test_skill_gates_discovered():
    """The four embedded review skills are wired in as gates; only the
    quality-gate-review verdict is blocking."""
    gates = {g.name: g for g in discover_gates()}
    for n in (
        "quality_gate_review",
        "ruthless_refactor",
        "pr_code_summary",
        "security_assessment",
    ):
        assert n in gates, f"skill gate missing: {n}"
    assert gates["quality_gate_review"].blocking is True
    assert gates["ruthless_refactor"].blocking is False
    assert gates["pr_code_summary"].blocking is False
    assert gates["security_assessment"].blocking is False


def test_skill_playbooks_load():
    """Every skill gate resolves its SKILL.md and the YAML frontmatter is stripped."""
    for name in (
        "pr-code-summarizer",
        "quality-gate-review",
        "ruthless-refactor",
        "security-assessment",
    ):
        body = skills.load_skill(name)
        assert body and not body.startswith("---")


def test_skill_outcome_coercion():
    """Verdict vocabularies (GO/REVIEW/NO-GO) and pass/warn/fail map correctly;
    an unknown word falls back to score banding."""
    assert skills._coerce_outcome("GO", 0.4) is P
    assert skills._coerce_outcome("no-go", 0.9) is F
    assert skills._coerce_outcome("REVIEW", 0.9) is W
    assert skills._coerce_outcome("pass", 0.0) is P
    assert skills._coerce_outcome("???", 0.9) is P  # banding: >=0.8
    assert skills._coerce_outcome("???", 0.5) is F  # banding: <0.6


def test_skill_json_parsing():
    """The judge tolerates fenced JSON and objects buried in prose."""
    assert skills._parse_json('```json\n{"score": 5}\n```')["score"] == 5
    assert skills._parse_json('noise {"outcome": "pass"} tail')["outcome"] == "pass"


def test_language_detection():
    assert _classify(["cmd/main.go", "go.mod"]) == {"go"}
    assert _classify(["src/main.rs", "Cargo.toml"]) == {"rust"}
    assert _classify(["src/app.ts", "tsconfig.json"]) == {"ts"}
    assert _classify(["index.js", "package.json"]) == {"node"}
    assert _classify(["a.py", "install.sh", "compose.yaml"]) == {
        "python",
        "shell",
        "yaml",
    }
    assert _classify(["README.md"]) == set()


def test_narrow_to_path(monkeypatch):
    from gandalf import scope
    from gandalf.scope import Scope, _narrow_to_path

    monkeypatch.setattr(scope, "_git", lambda args, cwd=".": "src/a.py\0src/b.py\0")
    # whole-tree scope: folder's tracked files become the changed set
    sc = _narrow_to_path(Scope("working-tree", "/repo", []), "src")
    assert sc.changed_files == ["src/a.py", "src/b.py"]
    assert sc.label == "working-tree:src"
    # staged scope: intersect the change set with the folder
    sc = _narrow_to_path(Scope("staged", "/repo", ["src/a.py", "other/c.py"]), "src")
    assert sc.changed_files == ["src/a.py"]
    # nothing tracked under the path is an error
    monkeypatch.setattr(scope, "_git", lambda args, cwd=".": "")
    try:
        _narrow_to_path(Scope("working-tree", "/repo", []), "nope")
        raise AssertionError("expected SystemExit")
    except SystemExit:
        pass


def test_language_filtering():
    """A Go-only change runs go gates + generic ones, NOT eslint/mypy/ruff."""
    gates = {g.name: g for g in discover_gates()}
    detected = {"go"}
    active = {
        n
        for n, g in gates.items()
        if not getattr(g, "langs", None) or (set(g.langs) & detected)
    }
    assert "go_build" in active and "go_test" in active
    assert "eslint" not in active and "tsc" not in active  # node/ts excluded
    assert "mypy" not in active and "ruff" not in active  # python excluded
    assert "gitleaks" in active and "semgrep" in active  # generic still run
    assert "codeql" in active  # codeql tags go among its langs → active


def test_rust_language_filtering():
    """A Rust-only change runs cargo gates, not go/node/python ones."""
    gates = {g.name: g for g in discover_gates()}
    detected = {"rust"}
    active = {
        n
        for n, g in gates.items()
        if not getattr(g, "langs", None) or (set(g.langs) & detected)
    }
    assert "cargo_build" in active and "clippy" in active and "cargo_test" in active
    assert "go_build" not in active and "eslint" not in active


# ---- LLM skill gates (grill-me / improve-codebase-architecture / well-architected) ----

SKILL_GATES = ("grill_me", "codebase_architecture", "well_architected")


def test_llm_skill_gates_discovered():
    """The three LLM skill gates each surface — generic (always run), non-blocking,
    and mapped to a category that renders in the scorecard."""
    gates = {g.name: g for g in discover_gates()}
    for name in SKILL_GATES:
        assert name in gates, f"skill gate {name} not discovered"
        g = gates[name]
        assert getattr(g, "blocking", False) is False  # advisory, never hard-red
        assert not getattr(g, "langs", None)  # generic: run on every change
        cat = _CATEGORY[name]
        assert cat in _GROUP_ORDER, f"{cat} won't render in the scorecard"


def test_skills_are_embedded():
    """Every slug a gate loads (skill + its dependencies) ships under skills/."""
    slugs = set()
    for g in discover_gates():
        slugs.update(getattr(g, "skills", ()) or ())
    assert {
        "grill-me",
        "grilling",
        "improve-codebase-architecture",
        "codebase-design",
        "well-architected",
    } <= slugs
    for slug in slugs:
        assert skillgate.load_skill(slug), f"skill {slug} not embedded / empty"


def test_parse_json_tolerates_fences_and_prose():
    assert skillgate.parse_json('```json\n{"score": 90}\n```')["score"] == 90
    assert skillgate.parse_json('sure:\n{"score": 5, "findings": []}\nok')["score"] == 5


def test_normalize_findings_maps_keys():
    out = skillgate._normalize_findings(
        [
            {
                "severity": "High",
                "title": "Shallow module",
                "detail": "deepen it",
                "location": "gandalf/x.py:10",
            },
            "bare string finding",
            {"nothing": "useful"},  # dropped: no finding/description text
        ]
    )
    assert out[0]["severity"] == "high"
    assert out[0]["finding"] == "Shallow module"
    assert out[0]["file"] == "gandalf/x.py:10"  # fmt_finding-compatible key
    assert out[1]["finding"] == "bare string finding"
    assert len(out) == 2


def _ctx(**meta):
    base = {"diff": "", "title": "", "body": "", "languages": ["python"]}
    base.update(meta)
    return GateContext(repo=".", workdir=".", changed_files=[], meta=base)


def _run(gate, ctx):
    return asyncio.run(gate.run(ctx))


def test_skill_gate_scores_and_maps_outcome(monkeypatch):
    """A high score → PASS, a low score → WARN (never FAIL), findings preserved."""
    from gandalf.gates.well_architected import WellArchitectedGate

    monkeypatch.setattr(
        llm,
        "chat",
        lambda *a, **k: '{"score": 95, "summary": "solid", "findings": []}',
    )
    res = _run(WellArchitectedGate(), _ctx(diff="+ added a retry with backoff"))
    assert res.outcome is GateOutcome.PASS and res.score == 0.95

    monkeypatch.setattr(
        llm,
        "chat",
        lambda *a, **k: (
            '{"score": 40, "summary": "gaps", '
            '"findings": [{"severity":"high","title":"No DR","detail":"add backups",'
            '"location":"infra.tf:3"}]}'
        ),
    )
    res = _run(WellArchitectedGate(), _ctx(diff="+ single-AZ database"))
    assert res.outcome is GateOutcome.WARN  # below threshold, but capped at amber
    assert any(f.get("finding") == "No DR" for f in res.findings)


def test_skill_gate_warns_when_judge_unavailable(monkeypatch):
    """LLM transport failure degrades to WARN — never a false PASS."""
    from gandalf.gates.codebase_architecture import CodebaseArchitectureGate

    def boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(llm, "chat", boom)
    res = _run(CodebaseArchitectureGate(), _ctx(diff="+ some code"))
    assert res.outcome is GateOutcome.WARN


def test_skill_gate_warns_with_nothing_in_scope(monkeypatch):
    """No diff, no files, no request → nothing to judge → WARN, no LLM call."""
    from gandalf.gates.grill_me import GrillMeGate

    def fail(*a, **k):  # must not be reached
        raise AssertionError("LLM should not be called with empty scope")

    monkeypatch.setattr(llm, "chat", fail)
    res = _run(GrillMeGate(), _ctx())
    assert res.outcome is GateOutcome.WARN


def test_atheris_gate_ignores_its_own_artifact_prefix_flag(monkeypatch, tmp_path):
    """A clean run must PASS even though the harness is invoked with
    -artifact_prefix=/tmp/atheris-crash-, which libFuzzer echoes back in its
    startup banner — a bare "crash" substring match would always self-match."""
    from gandalf.gates import dynamic

    fuzz_dir = tmp_path / "tests" / "fuzz"
    fuzz_dir.mkdir(parents=True)
    (fuzz_dir / "fuzz_adapters.py").write_text("")

    clean_log = (
        "INFO: Running with entropic power schedule\n"
        "artifact_prefix='/tmp/atheris-crash-'; Test unit written to ...\n"
        "#524288\tDONE   cov: 57 ft: 113 corp: 12/475b\n"
        "Done 702348 runs in 61 second(s)\n"
    )
    ctx = GateContext(repo=".", workdir=str(tmp_path), changed_files=[], meta={})
    monkeypatch.setattr(
        dynamic, "_run", lambda *a, **k: asyncio.sleep(0, result=(0, clean_log, ""))
    )
    res = _run(dynamic.AtherisGate(), ctx)
    assert res.outcome is GateOutcome.PASS

    crash_log = "==12345==ERROR: libFuzzer: deadly signal\n"
    monkeypatch.setattr(
        dynamic, "_run", lambda *a, **k: asyncio.sleep(0, result=(77, "", crash_log))
    )
    res = _run(dynamic.AtherisGate(), ctx)
    assert res.outcome is GateOutcome.FAIL


if __name__ == "__main__":
    test_aggregate_rag()
    test_aggregate_score()
    test_discovery_finds_builtins()
    test_skill_gates_discovered()
    test_skill_playbooks_load()
    test_skill_outcome_coercion()
    test_skill_json_parsing()
    test_language_detection()
    test_language_filtering()
    test_llm_skill_gates_discovered()
    test_skills_are_embedded()
    test_parse_json_tolerates_fences_and_prose()
    test_normalize_findings_maps_keys()
    print(
        "ok (run `pytest gandalf/test_gandalf.py` for the monkeypatch-based gate tests)"
    )
