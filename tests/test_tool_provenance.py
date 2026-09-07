"""Which scanner ran, and from where.

The same gate resolves differently on two machines — host binary here, container
there — and the findings differ with it. The run has to say which.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from gandalf import plugins, toolrun
from gandalf.outputs import tool_report
from gandalf.summary import _tools_line


# The stand-ins for `shutil.which` and the image probe, as named functions
# rather than lambdas: a lambda cannot carry the types, and these four say what
# they mean at the call site.
def _on_path(binary: str) -> str:
    return "/usr/bin/" + binary


def _not_on_path(binary: str) -> str | None:
    return None


def _in_image(binary: str) -> bool:
    return True


def _not_in_image(binary: str) -> bool:
    return False


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    plugins.reset_tool_sources()
    yield
    plugins.reset_tool_sources()


def test_host_resolution_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(toolrun.shutil, "which", _on_path)
    toolrun._dockerize(["ruff", "check"], "/tmp")
    assert plugins.tool_sources() == {"ruff": "host"}


def test_image_resolution_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(toolrun.shutil, "which", _not_on_path)
    monkeypatch.setattr(toolrun, "_via_image", _in_image)
    cmd = toolrun._dockerize(["trivy", "fs", "."], "/tmp")
    assert cmd[0] == "docker"
    assert plugins.tool_sources() == {"trivy": "image"}


def test_an_unresolvable_tool_is_not_claimed_to_have_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(toolrun.shutil, "which", _not_on_path)
    monkeypatch.setattr(toolrun, "_via_image", _not_in_image)
    toolrun._dockerize(["nope"], "/tmp")
    assert plugins.tool_sources() == {}


def test_first_resolution_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(toolrun.shutil, "which", _on_path)
    toolrun._dockerize(["ruff"], "/tmp")
    monkeypatch.setattr(toolrun.shutil, "which", _not_on_path)
    monkeypatch.setattr(toolrun, "_via_image", _in_image)
    toolrun._dockerize(["ruff"], "/tmp")
    assert plugins.tool_sources()["ruff"] == "host"


def test_reset_clears_process_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(toolrun.shutil, "which", _on_path)
    toolrun._dockerize(["ruff"], "/tmp")
    plugins.reset_tool_sources()
    assert plugins.tool_sources() == {}


def test_report_names_the_image_only_when_one_was_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugins, "tool_sources", lambda: {"ruff": "host"})
    assert "image" not in tool_report("/tmp", False)
    monkeypatch.setattr(plugins, "tool_sources", lambda: {"trivy": "image"})
    monkeypatch.setattr(plugins, "tools_image_id", lambda: "sha256:deadbeef")
    block = tool_report("/tmp", False)
    assert block["image"] == {"name": plugins.TOOLS_IMAGE, "id": "sha256:deadbeef"}
    assert block["resolved"]["trivy"] == {"source": "image"}


def test_versions_are_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugins, "tool_sources", lambda: {"ruff": "host"})
    assert "version" not in tool_report("/tmp", False)["resolved"]["ruff"]

    async def fake(workdir: str) -> dict[str, str]:
        return {"ruff": "ruff 0.15.8"}

    monkeypatch.setattr(plugins, "tool_versions", fake)
    got = tool_report("/tmp", True)["resolved"]["ruff"]
    assert got == {"source": "host", "version": "ruff 0.15.8"}


def test_no_tools_no_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugins, "tool_sources", dict)
    assert tool_report("/tmp", True) == {}
    assert _tools_line({}) == ""


def test_footer_line_counts_both_sources() -> None:
    tools = {
        "resolved": {"ruff": {"source": "host"}, "trivy": {"source": "image"}},
        "image": {"name": "gandalf-tools", "id": "sha256:abcdef0123456789"},
    }
    line = _tools_line(tools)
    assert "1 from PATH" in line
    assert "1 from gandalf-tools" in line
    assert "sha256:abcdef012" in line


def test_footer_lists_versions_when_probed() -> None:
    tools = {"resolved": {"ruff": {"source": "host", "version": "ruff 0.15.8"}}}
    assert "ruff (host) ruff 0.15.8" in _tools_line(tools)
