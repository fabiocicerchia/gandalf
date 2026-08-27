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
import sys

import pytest

from gandalf.base import GateContext, GateOutcome
from gandalf.gates import _toolchain
from gandalf.plugins import discover_gates, scannable_files, tracked_files
from gandalf.scope import _classify

GATES = {g.name: g for g in discover_gates()}

JAVA = ("java_build", "checkstyle", "ktlint", "java_test")
RUBY = ("ruby_syntax", "rubocop", "bundler_audit", "ruby_test")
PHP = ("php_syntax", "phpcs", "composer_audit", "php_test")
CPP = ("cpp_build", "cppcheck", "cpp_test")
DOTNET = ("dotnet_build", "dotnet_format", "dotnet_audit", "dotnet_test")
ALL = JAVA + RUBY + PHP + CPP + DOTNET


def _repo(tmp_path, files: dict[str, str]) -> str:
    """A git repo with these files staged — gates read git-tracked paths."""
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    # The tracked-file listing is cached per workdir and every fixture is a new
    # tree in a reused temp root, so the cache has to go with the fixture.
    tracked_files.cache_clear()
    scannable_files.cache_clear()
    return str(tmp_path)


def _run(name: str, workdir: str, changed: list[str] | None = None):
    ctx = GateContext(repo=workdir, workdir=workdir, changed_files=changed or [])
    return asyncio.run(GATES[name].run(ctx))


def test_every_ecosystem_gate_is_discovered():
    assert set(ALL) <= set(GATES), f"missing: {set(ALL) - set(GATES)}"


def test_only_the_build_and_syntax_gates_are_blocking():
    """A tree that does not compile or does not parse is a hard stop; a linter
    or an advisory scan never is — same split as the Go and Rust suites."""
    blocking = {n for n in ALL if GATES[n].blocking}
    assert blocking == {"java_build", "ruby_syntax", "php_syntax", "dotnet_build"}


def test_cpp_build_is_advisory():
    """C++ is the exception: a missing system library is the machine's fault,
    not the change's, so this one informs rather than blocks."""
    assert GATES["cpp_build"].blocking is False


@pytest.mark.parametrize("name", ALL)
def test_absent_ecosystem_is_a_green_skip(tmp_path, name):
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
    tmp_path, monkeypatch, name, files, binary
):
    """Amber, never a pass: the gate had something to look at and could not."""
    # Both namespaces: the base class asks _toolchain, and a gate that picks its
    # own tool (maven vs gradle, vendor/bin vs global) asks its own module.
    monkeypatch.setattr(_toolchain, "tool_missing", lambda _b: True)
    gate_module = sys.modules[type(GATES[name]).__module__]
    if hasattr(gate_module, "tool_missing"):
        monkeypatch.setattr(gate_module, "tool_missing", lambda _b: True)
    r = _run(name, _repo(tmp_path, files))
    assert r.outcome is GateOutcome.WARN, r.summary
    assert binary in r.summary and "skipped" in r.summary


def test_project_dir_finds_the_shallowest_manifest(tmp_path):
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
    assert _toolchain.project_dir(ctx, ("*.csproj",)).endswith("src/App")
    assert _toolchain.project_dir(ctx, ("*.sln",)) is None


def test_counted_scoring_matches_the_house_rules():
    c = _toolchain.counted
    assert c("g", 0, "l").outcome is GateOutcome.PASS
    assert c("g", 3, "l").outcome is GateOutcome.WARN
    assert c("g", 4, "l").outcome is GateOutcome.FAIL
    assert c("g", 10, "l").score == 0.0
    assert c("g", 99, "l").score == 0.0  # clamped, never negative


def test_sources_prefers_the_change_over_the_tree(tmp_path):
    workdir = _repo(tmp_path, {"a.rb": "1\n", "b.rb": "2\n", "c.py": "x = 1\n"})
    whole = GateContext(repo=workdir, workdir=workdir)
    assert _toolchain.sources(whole, ".rb") == ["a.rb", "b.rb"]
    scoped = GateContext(repo=workdir, workdir=workdir, changed_files=["b.rb", "c.py"])
    assert _toolchain.sources(scoped, ".rb") == ["b.rb"]


def test_language_markers_classify_the_new_ecosystems():
    assert _classify(["pom.xml"]) == {"java"}
    assert _classify(["src/Main.kt"]) == {"kotlin"}
    assert _classify(["Gemfile"]) == {"ruby"}
    assert _classify(["composer.json"]) == {"php"}
    assert _classify(["CMakeLists.txt"]) == {"cpp"}
    assert _classify(["src/main.cpp", "src/util.h"]) == {"cpp", "c"}
    assert _classify(["App/App.csproj", "App/Program.cs"]) == {"dotnet"}


def test_a_stray_ruby_config_does_not_make_a_ruby_project(tmp_path):
    """`.mdl_style.rb` is a markdown-lint config, and this repo has one. It is
    worth a parse check and nothing else — a linter and a test runner turning
    amber over one config file is exactly the false positive that makes a
    polyglot gate suite unusable."""
    workdir = _repo(tmp_path, {"a.py": "x = 1\n", ".mdl_style.rb": "all\n"})
    for name in ("rubocop", "ruby_test", "bundler_audit"):
        r = _run(name, workdir)
        assert r.outcome is GateOutcome.PASS and "not in this tree" in r.summary


@pytest.mark.skipif(shutil.which("ruby") is None, reason="needs ruby")
def test_ruby_syntax_reads_real_ruby(tmp_path):
    """The one gate this machine can always exercise end to end."""
    good = _run("ruby_syntax", _repo(tmp_path / "ok", {"lib/a.rb": "def hi\nend\n"}))
    # The summary too: a self-skip is also a green pass, and that would hide a
    # gate that never looked at the file.
    assert good.outcome is GateOutcome.PASS and "1 file(s) parse" in good.summary

    bad = _run("ruby_syntax", _repo(tmp_path / "bad", {"lib/a.rb": "def hi\n"}))
    assert bad.outcome is GateOutcome.FAIL
    assert bad.score == 0.0
    assert bad.findings and bad.findings[0]["file"] == "lib/a.rb"


@pytest.mark.skipif(
    shutil.which("cmake") is None or shutil.which("c++") is None, reason="needs cmake"
)
def test_cpp_build_compiles_and_fails_honestly(tmp_path):
    cml = (
        "cmake_minimum_required(VERSION 3.10)\n"
        "project(demo CXX)\nadd_executable(demo main.cpp)\n"
    )
    ok = _repo(tmp_path / "ok", {"CMakeLists.txt": cml, "main.cpp": "int main(){}\n"})
    built = _run("cpp_build", ok)
    assert built.outcome is GateOutcome.PASS and "compiles" in built.summary

    broken = _repo(
        tmp_path / "bad",
        {"CMakeLists.txt": cml, "main.cpp": "int main(){ return nope; }\n"},
    )
    r = _run("cpp_build", broken)
    assert r.outcome is GateOutcome.FAIL and r.score == 0.0
