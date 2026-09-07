"""Tests for config loading + gate selection. Run: pytest gandalf/test_config.py"""

from __future__ import annotations

from pathlib import Path

import pytest

from gandalf import config
from gandalf.base import GateContext, GateOutcome, GateResult


class _G:
    blocking = False

    def __init__(self, name: str) -> None:
        self.name = name

    async def run(self, ctx: GateContext) -> GateResult:
        return GateResult(self.name, GateOutcome.PASS, 1.0, "ok")


def _write(tmp: Path | str, text: str) -> str:
    p = str(Path(tmp) / ".gandalf.toml")
    with Path(p).open("w") as fh:
        fh.write(text)
    return p


def test_missing_config_is_empty(tmp_path: Path) -> None:
    c = config.load(str(tmp_path))
    assert c.only == set()
    assert c.skip == set()
    assert c.path == ""
    assert c.concurrency is None


def test_load_and_sections(tmp_path: Path) -> None:
    _write(
        str(tmp_path),
        "[gandalf]\nskip=['atheris']\nconcurrency=6\n[gandalf.verdict]\nfail_on='warn'\n",
    )
    c = config.load(str(tmp_path))
    assert c.path.endswith(".gandalf.toml")
    assert c.skip == {"atheris"}
    assert c.concurrency == 6
    assert c.section("verdict") == {"fail_on": "warn"}
    assert c.section("nope") == {}


def test_broken_config_falls_back(tmp_path: Path) -> None:
    _write(str(tmp_path), "this is not = valid toml [[[")
    c = config.load(str(tmp_path))  # must not raise
    assert c.only == set()
    assert c.skip == set()


def test_select_only_and_skip() -> None:
    gates = [_G("ruff"), _G("mypy"), _G("gitleaks")]
    kept, disabled = config.Config({"only": ["ruff", "mypy"]}).select(gates)
    assert {g.name for g in kept} == {"ruff", "mypy"}
    assert disabled == ["gitleaks"]
    kept, disabled = config.Config({"skip": ["mypy"]}).select(gates)
    assert {g.name for g in kept} == {"ruff", "gitleaks"}
    assert disabled == ["mypy"]
    # skip wins over only
    kept, disabled = config.Config({"only": ["ruff"], "skip": ["ruff"]}).select(gates)
    assert kept == []
    assert "ruff" in disabled


def test_explicit_and_env_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write(str(tmp_path), "[gandalf]\nskip=['x']\n")
    assert config.load(None, p).skip == {"x"}
    monkeypatch.setenv("GANDALF_CONFIG", p)
    assert config.load(None).skip == {"x"}


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        test_missing_config_is_empty(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_load_and_sections(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_broken_config_falls_back(Path(d))
    test_select_only_and_skip()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / ".gandalf.toml"
        p.write_text("[gandalf]\nskip=['x']\n")
        assert config.load(None, str(p)).skip == {"x"}
