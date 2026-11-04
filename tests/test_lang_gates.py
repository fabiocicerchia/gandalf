"""The five per-ecosystem gate suites: Java/Kotlin, Ruby, PHP, C/C++, .NET.

What has to hold for all of them, whatever tooling the machine running these
tests happens to have: an ecosystem that is not in the tree is a green self-skip,
a toolchain that is not installed is amber and says which binary is missing, and
nothing ever reports a clean pass because a tool failed to run.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates import _toolchain
from gandalf.plugins import discover_gates, scannable_files, tracked_files
from gandalf.scope import classify

GATES = {g.name: g for g in discover_gates()}

JAVA = ("java_build", "checkstyle", "ktlint", "java_test")
RUBY = ("ruby_syntax", "rubocop", "bundler_audit", "ruby_test")
PHP = ("php_syntax", "phpcs", "composer_audit", "php_test")
CPP = ("cpp_build", "cppcheck", "cpp_test")
DOTNET = ("dotnet_build", "dotnet_format", "dotnet_audit", "dotnet_test")
ALL = JAVA + RUBY + PHP + CPP + DOTNET


def _repo(tmp_path: Path, files: dict[str, str]) -> str:
    """A git repo with these files staged — gates read git-tracked paths."""
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # nosec B603 B607
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)  # nosec B603 B607
    # The tracked-file listing is cached per workdir and every fixture is a new
    # tree in a reused temp root, so the cache has to go with the fixture.
    tracked_files.cache_clear()
    scannable_files.cache_clear()
    return str(tmp_path)


def _run(name: str, workdir: str, changed: list[str] | None = None) -> GateResult:
    ctx = GateContext(repo=workdir, workdir=workdir, changed_files=changed or [])
    return asyncio.run(GATES[name].run(ctx))


def test_every_ecosystem_gate_is_discovered() -> None:
    assert set(ALL) <= set(GATES), f"missing: {set(ALL) - set(GATES)}"


def test_only_the_build_and_syntax_gates_are_blocking() -> None:
    """A tree that does not compile or does not parse is a hard stop; a linter
    or an advisory scan never is — same split as the Go and Rust suites."""
    blocking = {n for n in ALL if GATES[n].blocking}
    assert blocking == {"java_build", "ruby_syntax", "php_syntax", "dotnet_build"}


def test_cpp_build_is_advisory() -> None:
    """C++ is the exception: a missing system library is the machine's fault,
    not the change's, so this one informs rather than blocks."""
    assert GATES["cpp_build"].blocking is False


@pytest.mark.parametrize("name", ALL)
def test_absent_ecosystem_is_a_green_skip(tmp_path: Path, name: str) -> None:
    """A Python-only repo must not go amber for every language it does not use."""
    workdir = _repo(tmp_path, {"a.py": "x = 1\n"})
    r = _run(name, workdir)
    assert r.outcome is GateOutcome.PASS, r.summary
    assert r.score == 1.0


@pytest.mark.parametrize(
    ("name", "files", "binary"),
    [
        ("java_build", {"pom.xml": "<project/>\n"}, "mvn"),
        (
            "checkstyle",
            {"pom.xml": "<project/>\n", "A.java": "class A {}\n"},
            "checkstyle",
        ),
        ("ktlint", {"A.kt": "fun main() {}\n"}, "ktlint"),
        ("rubocop", {"Gemfile": "source 'x'\n"}, "rubocop"),
        ("bundler_audit", {"Gemfile.lock": "GEM\n"}, "bundle-audit"),
        ("php_syntax", {"a.php": "<?php\n"}, "php"),
        ("composer_audit", {"composer.lock": "{}\n"}, "composer"),
        ("cppcheck", {"a.cpp": "int main(){}\n"}, "cppcheck"),
        ("dotnet_build", {"App/App.csproj": "<Project/>\n"}, "dotnet"),
    ],
)
def test_missing_toolchain_warns_and_names_the_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, files: dict[str, str], binary: str
) -> None:
    """Amber, never a pass: the gate had something to look at and could not."""

    # Both namespaces: the base class asks _toolchain, and a gate that picks its
    # own tool (maven vs gradle, vendor/bin vs global) asks its own module.
    # That second namespace has to come off the class itself. Looking it up as
    # sys.modules[cls.__module__] finds the wrong object: discover_gates()
    # re-executes every gate file on each call and rebinds `gandalf_gate_<stem>`
    # to a fresh module, so once another test module has discovered gates the
    # entry under that name is no longer the namespace this class resolves
    # against — and the gate would go on to shell out to a real mvn.
    def missing(_b: str) -> bool:
        return True

    monkeypatch.setattr(_toolchain, "tool_missing", missing)
    check = getattr(type(GATES[name]), "check", None)
    gate_globals: dict[str, Any] = getattr(check, "__globals__", {})
    if "tool_missing" in gate_globals:
        monkeypatch.setitem(gate_globals, "tool_missing", missing)
    r = _run(name, _repo(tmp_path, files))
    assert r.outcome is GateOutcome.WARN, r.summary
    assert binary in r.summary
    assert "skipped" in r.summary


def test_project_dir_finds_the_shallowest_manifest(tmp_path: Path) -> None:
    """A .csproj two directories down is still a .NET project, and the tool has
    to run where the manifest is — the repo root would find nothing."""
    workdir = _repo(
        tmp_path,
        {
            "src/App/App.csproj": "<Project/>\n",
            "src/App/Nested/Deep.csproj": "<Project/>\n",
        },
    )
    ctx = GateContext(repo=workdir, workdir=workdir)
    found = _toolchain.project_dir(ctx, ("*.csproj",))
    assert found is not None
    assert found.endswith("src/App")
    assert _toolchain.project_dir(ctx, ("*.sln",)) is None


def test_counted_scoring_matches_the_house_rules() -> None:
    c = _toolchain.counted
    assert c("g", 0, "l").outcome is GateOutcome.PASS
    assert c("g", 3, "l").outcome is GateOutcome.WARN
    assert c("g", 4, "l").outcome is GateOutcome.FAIL
    assert c("g", 10, "l").score == 0.0
    assert c("g", 99, "l").score == 0.0  # clamped, never negative


def test_sources_prefers_the_change_over_the_tree(tmp_path: Path) -> None:
    workdir = _repo(tmp_path, {"a.rb": "1\n", "b.rb": "2\n", "c.py": "x = 1\n"})
    whole = GateContext(repo=workdir, workdir=workdir)
    assert _toolchain.sources(whole, ".rb") == ["a.rb", "b.rb"]
    scoped = GateContext(repo=workdir, workdir=workdir, changed_files=["b.rb", "c.py"])
    assert _toolchain.sources(scoped, ".rb") == ["b.rb"]


def test_language_markers_classify_the_new_ecosystems() -> None:
    assert classify(["pom.xml"]) == {"java"}
    assert classify(["src/Main.kt"]) == {"kotlin"}
    assert classify(["Gemfile"]) == {"ruby"}
    assert classify(["composer.json"]) == {"php"}
    assert classify(["CMakeLists.txt"]) == {"cpp"}
    assert classify(["src/main.cpp", "src/util.h"]) == {"cpp", "c"}
    assert classify(["App/App.csproj", "App/Program.cs"]) == {"dotnet"}


def test_a_stray_ruby_config_does_not_make_a_ruby_project(tmp_path: Path) -> None:
    """`.mdl_style.rb` is a markdown-lint config, and this repo has one. It is
    worth a parse check and nothing else — a linter and a test runner turning
    amber over one config file is exactly the false positive that makes a
    polyglot gate suite unusable."""
    workdir = _repo(tmp_path, {"a.py": "x = 1\n", ".mdl_style.rb": "all\n"})
    for name in ("rubocop", "ruby_test", "bundler_audit"):
        r = _run(name, workdir)
        assert r.outcome is GateOutcome.PASS
        assert "not in this tree" in r.summary


@pytest.mark.skipif(shutil.which("ruby") is None, reason="needs ruby")
def test_ruby_syntax_reads_real_ruby(tmp_path: Path) -> None:
    """The one gate this machine can always exercise end to end."""
    good = _run("ruby_syntax", _repo(tmp_path / "ok", {"lib/a.rb": "def hi\nend\n"}))
    # The summary too: a self-skip is also a green pass, and that would hide a
    # gate that never looked at the file.
    assert good.outcome is GateOutcome.PASS
    assert "1 file(s) parse" in good.summary

    bad = _run("ruby_syntax", _repo(tmp_path / "bad", {"lib/a.rb": "def hi\n"}))
    assert bad.outcome is GateOutcome.FAIL
    assert bad.score == 0.0
    assert bad.findings
    assert bad.findings[0]["file"] == "lib/a.rb"


@pytest.mark.skipif(shutil.which("cmake") is None or shutil.which("c++") is None, reason="needs cmake")
def test_cpp_build_compiles_and_fails_honestly(tmp_path: Path) -> None:
    cml = "cmake_minimum_required(VERSION 3.10)\nproject(demo CXX)\nadd_executable(demo main.cpp)\n"
    ok = _repo(tmp_path / "ok", {"CMakeLists.txt": cml, "main.cpp": "int main(){}\n"})
    built = _run("cpp_build", ok)
    assert built.outcome is GateOutcome.PASS
    assert "compiles" in built.summary

    broken = _repo(
        tmp_path / "bad",
        {"CMakeLists.txt": cml, "main.cpp": "int main(){ return nope; }\n"},
    )
    r = _run("cpp_build", broken)
    assert r.outcome is GateOutcome.FAIL
    assert r.score == 0.0


def test_codeql_whole_tree_analyzes_only_detected_languages() -> None:
    from gandalf.gates.codeql import _codeql_langs

    # a whole-tree run has no changed files: the detected languages decide, not every CodeQL language
    assert _codeql_langs([], ["python", "shell"]) == ["python"]
    assert _codeql_langs([], ["go", "ts", "node"]) == ["go", "javascript"]
    assert _codeql_langs([], ["shell"]) == []
    # a scoped run: the changed files decide
    assert _codeql_langs(["a.py"], ["go"]) == ["python"]
    # nothing known at all: every language, as before
    assert _codeql_langs([], None) == ["go", "javascript", "python"]


def test_codeql_docker_keeps_compiled_queries_between_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from gandalf.gates import codeql

    calls: list[list[str]] = []

    async def fake_run_tool(argv: list[str], *_: Any) -> tuple[int, str, str]:
        calls.append(argv)
        return 1, "", ""  # stop after the first step: only the argv matters here

    monkeypatch.setattr(codeql, "run_tool", fake_run_tool)
    monkeypatch.setattr(codeql, "_CACHE", tmp_path / "cache")
    ctx = GateContext(repo=str(tmp_path), workdir=str(tmp_path))
    asyncio.run(codeql.CodeqlGate()._analyze(ctx, str(tmp_path), "python", str(tmp_path / "p.sarif"), have_host=False))
    argv = calls[0]
    assert f"{tmp_path / 'cache'}:/caches" in argv
    assert "--common-caches=/caches" in argv
    assert (tmp_path / "cache").is_dir()  # made before docker could make it root-owned


def test_python_tests_gate_skips_a_tree_with_no_tests(tmp_path: Path) -> None:
    """pytest exits 5 when it collects nothing — that is no signal, not a failure."""
    workdir = _repo(tmp_path, {"pyproject.toml": "", "requirements.txt": ""})
    res = _run("tests", workdir)
    assert res.outcome is GateOutcome.WARN
    assert getattr(res, "_unavailable", False)
    assert "no tests collected" in res.summary
