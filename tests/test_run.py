"""Tests for the gate runner: bounded concurrency + error isolation.
Run: pytest gandalf/test_run.py"""

from __future__ import annotations

import asyncio
import json
import subprocess

from gandalf import plugins
from gandalf.__main__ import _gate_timeout, _resolve_concurrency, _run_gates, main
from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.config import Config
from gandalf.fixers import _files_note, _touched, _tree_state, run_fixers


class _Slow:
    def __init__(self, name, tracker) -> None:
        self.name = name
        self.blocking = False
        self._t = tracker

    async def run(self, ctx):
        self._t["live"] += 1
        self._t["peak"] = max(self._t["peak"], self._t["live"])
        await asyncio.sleep(0.02)
        self._t["live"] -= 1
        return GateResult(self.name, GateOutcome.PASS, 1.0, "ok")


class _Broken:
    name = "broken"
    blocking = False

    async def run(self, ctx):
        raise RuntimeError("boom")


_CTX = GateContext(repo=".", workdir=".")


def test_concurrency_is_bounded() -> None:
    t = {"live": 0, "peak": 0}
    gates = [_Slow(f"g{i}", t) for i in range(10)]
    res = asyncio.run(_run_gates(gates, _CTX, limit=3))
    assert len(res) == 10
    assert t["peak"] == 3


def test_unbounded_runs_all_at_once() -> None:
    t = {"live": 0, "peak": 0}
    gates = [_Slow(f"g{i}", t) for i in range(6)]
    asyncio.run(_run_gates(gates, _CTX, limit=0))
    assert t["peak"] == 6


def test_broken_gate_degrades_to_warn() -> None:
    res = asyncio.run(_run_gates([_Broken()], _CTX, limit=1))
    assert res[0].outcome is GateOutcome.WARN
    assert "boom" in res[0].summary


class _Fixer:
    name = "fixme"
    blocking = False

    async def fix(self, ctx):
        return (True, "did a thing")


class _NoFix:
    name = "nofix"
    blocking = False

    async def run(self, ctx):
        return GateResult(self.name, GateOutcome.PASS, 1.0, "ok")


class _BadFixer:
    name = "badfix"
    blocking = False

    async def fix(self, ctx):
        raise RuntimeError("nope")


def test_run_fixers_collects_and_skips() -> None:
    res = asyncio.run(run_fixers([_Fixer(), _NoFix()], _CTX))
    # only the gate exposing fix() is run
    assert res == [("fixme", True, "did a thing")]


def test_run_fixers_isolates_errors() -> None:
    res = asyncio.run(run_fixers([_BadFixer()], _CTX))
    assert res[0][0] == "badfix"
    assert res[0][1] is False
    assert "nope" in res[0][2]


def test_resolve_concurrency_precedence(monkeypatch) -> None:
    monkeypatch.delenv("GANDALF_CONCURRENCY", raising=False)
    assert _resolve_concurrency(5, Config()) == 5  # cli wins
    assert _resolve_concurrency(None, Config({"concurrency": 7})) == 7  # then config
    monkeypatch.setenv("GANDALF_CONCURRENCY", "4")
    assert _resolve_concurrency(None, Config({"concurrency": 7})) == 4  # env beats config


def test_gate_timeout_resolution() -> None:
    ts = {"default": 60, "semgrep": 300}
    assert _gate_timeout("semgrep", ts) == 300  # per-gate key wins
    assert _gate_timeout("ruff", ts) == 60  # falls to default
    assert _gate_timeout("ruff", {}) is None  # no section → global default
    assert _gate_timeout("x", {"x": "abc"}) is None  # junk ignored


def test_per_gate_timeout_visible_in_run() -> None:
    seen = {}

    class _Probe:
        def __init__(self, n) -> None:
            self.name = n
            self.blocking = False

        async def run(self, ctx):
            seen[self.name] = plugins.GATE_TIMEOUT.get()
            return GateResult(self.name, GateOutcome.PASS, 1.0, "ok")

    ts = {"default": 60, "semgrep": 300}
    asyncio.run(_run_gates([_Probe("semgrep"), _Probe("ruff")], _CTX, limit=2, timeouts=ts))
    assert seen == {"semgrep": 300, "ruff": 60}


if __name__ == "__main__":
    import os

    os.environ.pop("GANDALF_CONCURRENCY", None)
    test_concurrency_is_bounded()
    test_unbounded_runs_all_at_once()
    test_broken_gate_degrades_to_warn()
    test_run_fixers_collects_and_skips()
    test_run_fixers_isolates_errors()
    test_gate_timeout_resolution()
    test_per_gate_timeout_visible_in_run()
    assert _resolve_concurrency(5, Config()) == 5


# --- report destinations: --out-dir / --no-trend --------------------------------
# End-to-end through main() in a throwaway git repo, with `only = ["build"]` so
# the run stays stdlib-fast (the build gate just compiles the Python in scope).


def _git(repo, *args) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=test", *args],
        cwd=repo,
        check=True,
    )


def _mkrepo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "ok.py").write_text("VALUE = 1\n")
    (repo / ".gandalf.toml").write_text('[gandalf]\nonly = ["build"]\n')
    _git(repo, "init", "-q", ".")
    _git(repo, "add", "-A")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "init")
    return repo


def test_out_dir_and_no_trend_keep_the_worktree_clean(tmp_path, monkeypatch, capsys) -> None:
    repo = _mkrepo(tmp_path)
    monkeypatch.chdir(repo)
    out = tmp_path / "artifacts" / "nested"  # missing parents must be created

    assert main(["--no-llm", "--no-trend", "--out-dir", str(out)]) == 0

    assert len(list(out.glob("gandalf-*.json"))) == 1
    assert len(list(out.glob("gandalf-*.html"))) == 1
    assert not (repo / "reports").exists()
    assert not (repo / ".gandalf-trend.jsonl").exists()
    assert str(out) in capsys.readouterr().out


def test_reports_default_to_the_repo_and_record_a_trend(tmp_path, monkeypatch) -> None:
    repo = _mkrepo(tmp_path)
    monkeypatch.chdir(repo)

    assert main(["--no-llm"]) == 0

    assert len(list((repo / "reports").glob("gandalf-*.json"))) == 1
    trend = json.loads((repo / ".gandalf-trend.jsonl").read_text().splitlines()[0])
    assert trend["score"] == 100


def test_stream_emits_one_ndjson_line_per_gate(tmp_path, monkeypatch, capsys) -> None:
    repo = _mkrepo(tmp_path)
    monkeypatch.chdir(repo)
    out = tmp_path / "artifacts"

    args = ["--no-llm", "--no-trend", "--no-html", "--stream", "--out-dir", str(out)]
    assert main(args) == 0

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{"event"')]
    assert events[0] == {"event": "start", "scope": "working-tree", "gates": 1}
    (gate,) = events[1:]
    assert gate["event"] == "gate"
    assert (gate["index"], gate["total"]) == (1, 1)
    assert gate["name"] == "build"
    assert gate["outcome"] == "pass"
    assert gate["category"] == "Build & tests"
    assert gate["findings"] == []
    assert isinstance(gate["duration"], float)


def test_stream_reports_cache_hits_too(tmp_path, monkeypatch, capsys) -> None:
    """A cached gate never runs, so nothing would report it — but a consumer's
    pane must still fill on a warm cache."""
    repo = _mkrepo(tmp_path)
    monkeypatch.chdir(repo)
    out = tmp_path / "artifacts"
    args = ["--no-llm", "--no-trend", "--no-html", "--cache", "--out-dir", str(out)]

    assert main(args) == 0  # cold: populates .gandalf-cache.json
    capsys.readouterr()
    assert main([*args, "--stream"]) == 0

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{"event"')]
    assert [e["event"] for e in events] == ["start", "gate"]
    assert events[1]["name"] == "build"


def test_stream_applies_baseline_suppression(tmp_path, monkeypatch, capsys) -> None:
    """A baselined finding must not flash up in a consumer's pane and then
    vanish when the report lands."""
    repo = _mkrepo(tmp_path)
    (repo / "src" / "broken.py").write_text("def oops(:\n")
    _git(repo, "add", "-A")  # tree scans cover tracked files, so it must be staged
    monkeypatch.chdir(repo)
    out = tmp_path / "artifacts"
    common = ["--no-llm", "--no-trend", "--no-html", "--out-dir", str(out)]

    # Red, and the finding streams through.
    assert main([*common, "--stream"]) == 1
    streamed = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{"event": "gate"')
    ]
    assert len(streamed[0]["findings"]) == 1

    # Accept it, then re-run: the gate now streams clean.
    assert main([*common, "--write-baseline"]) == 0
    capsys.readouterr()
    assert main([*common, "--stream"]) == 0
    streamed = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{"event": "gate"')
    ]
    assert streamed[0]["findings"] == []
    assert streamed[0]["outcome"] == "pass"


def test_exclude_narrows_the_scan_end_to_end(tmp_path, monkeypatch, capsys) -> None:
    repo = _mkrepo(tmp_path)
    (repo / "src" / "generated").mkdir()
    (repo / "src" / "generated" / "broken.py").write_text("def oops(:\n")
    _git(repo, "add", "-A")
    monkeypatch.chdir(repo)
    out = tmp_path / "artifacts"
    args = ["--no-llm", "--no-trend", "--no-html", "--stream", "--out-dir", str(out)]

    # The generated file does not compile, so the build gate fails on it.
    assert main([*args]) == 1
    gate = next(
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{"event": "gate"')
    )
    assert [f["path"] for f in gate["findings"]] == ["src/generated/broken.py"]

    # Excluded, the gate never reads it — and the run goes green.
    assert main([*args, "--exclude", "src/generated"]) == 0
    gate = next(
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{"event": "gate"')
    )
    assert gate["findings"] == []


def test_exclude_can_come_from_the_config_file(tmp_path, monkeypatch, capsys) -> None:
    repo = _mkrepo(tmp_path)
    (repo / "vendor").mkdir()
    (repo / "vendor" / "broken.py").write_text("def oops(:\n")
    (repo / ".gandalf.toml").write_text('[gandalf]\nonly = ["build"]\nexclude = ["vendor"]\n')
    _git(repo, "add", "-A")
    monkeypatch.chdir(repo)

    args = ["--no-llm", "--no-trend", "--no-html", "--out-dir", str(tmp_path / "a")]
    assert main(args) == 0
    capsys.readouterr()


def test_payload_gates_carry_their_category(tmp_path, monkeypatch) -> None:
    repo = _mkrepo(tmp_path)
    monkeypatch.chdir(repo)
    out = tmp_path / "artifacts"

    assert main(["--no-llm", "--no-trend", "--no-html", "--out-dir", str(out)]) == 0

    payload = json.loads(next(out.glob("gandalf-*.json")).read_text())
    assert [g["category"] for g in payload["gates"]] == ["Build & tests"]


# --- --fix: what a fixer actually changed ---------------------------------------
# A fixer's own account of its work is whatever its tool prints, and several of
# them print nothing useful (eslint) or exit non-zero on a successful run. The
# runner measures the worktree instead — these cover that measurement.


def test_files_note_lists_and_truncates() -> None:
    assert _files_note(["a.py", "b.py"]) == "a.py, b.py"
    note = _files_note([f"f{i}.py" for i in range(7)])
    assert note.startswith("f0.py, ")
    assert note.endswith("…+2 more")


def test_touched_spots_content_changes_not_just_new_files() -> None:
    before = {"a.py": "h1", "b.py": "same"}
    after = {"a.py": "h2", "b.py": "same", "c.py": "new"}
    assert _touched(before, after) == ["a.py", "c.py"]


def test_tree_state_outside_a_repo_is_silent(tmp_path) -> None:
    assert _tree_state(str(tmp_path)) == {}


def test_fixer_report_comes_from_the_worktree(tmp_path) -> None:
    """The fixer under-reports (says it changed nothing); the runner corrects it
    from the diff, which is what `eslint --fix` and `golangci-lint --fix` need."""
    repo = _mkrepo(tmp_path)

    class _Rewriter:
        name = "rewriter"
        blocking = False

        async def fix(self, ctx):
            path = repo / "src" / "ok.py"
            path.write_text(path.read_text().replace("VALUE = 1", "VALUE = 2"))
            return (False, "rewriter ran")

    (name, changed, msg) = asyncio.run(run_fixers([_Rewriter()], GateContext(repo=str(repo), workdir=str(repo))))[0]
    assert (name, changed) == ("rewriter", True)
    assert msg == "rewriter ran — src/ok.py"


def test_a_fixer_that_changes_nothing_is_reported_as_such(tmp_path) -> None:
    repo = _mkrepo(tmp_path)

    class _Idle:
        name = "idle"
        blocking = False

        async def fix(self, ctx):
            return (False, "nothing to do")

    res = asyncio.run(run_fixers([_Idle()], GateContext(repo=str(repo), workdir=str(repo))))
    assert res == [("idle", False, "nothing to do")]
