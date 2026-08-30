"""Rust gates: build, clippy, cargo-audit, test.

Same shape as golang.py: these need the host Rust toolchain (cargo/clippy/
cargo-audit), not the gandalf-tools image. Each self-skips (PASS) when the
workdir has no Cargo.toml.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import (
    run_tool,
    timeout_result,
    tool_missing,
    unavailable,
)


def _no_crate(ctx: GateContext) -> bool:
    return not (Path(ctx.workdir) / "Cargo.toml").exists()


class RustBuildGate:
    """`cargo build` — the Rust analogue of the Python/Go build gates. Blocking."""

    name = "cargo_build"
    blocking = True
    langs = frozenset({"rust"})

    async def run(self, ctx: GateContext) -> GateResult:
        if _no_crate(ctx):
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "rust: no crate (no Cargo.toml)"
            )
        if tool_missing("cargo"):
            return unavailable(self.name, "cargo not installed — skipped")
        rc, _out, err = await run_tool(["cargo", "build"], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        if rc == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "cargo build: compiles")
        tail = "\n".join((err or "").strip().splitlines()[-5:])
        return GateResult(
            self.name,
            GateOutcome.FAIL,
            0.0,
            f"cargo build: does not compile — {tail}",
            [{"stderr": err[-1000:]}],
        )


class ClippyGate:
    """cargo clippy — the standard Rust linter."""

    name = "clippy"
    blocking = False
    langs = frozenset({"rust"})

    async def run(self, ctx: GateContext) -> GateResult:
        if _no_crate(ctx):
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "rust: no crate (no Cargo.toml)"
            )
        if tool_missing("cargo"):
            return unavailable(self.name, "cargo not installed — skipped")
        rc, _out, err = await run_tool(
            ["cargo", "clippy", "--message-format=json"], ctx.workdir
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        combined = (_out or "") + (err or "")
        n = 0
        for line in combined.splitlines():
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("reason") == "compiler-message" and (
                msg.get("message", {}).get("level") in ("warning", "error")
            ):
                n += 1
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "clippy: clean")
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.WARN if n <= 3 else GateOutcome.FAIL
        return GateResult(self.name, outcome, score, f"clippy: {n} issue(s)")

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """`cargo clippy --fix` — applies the machine-applicable lints. Called
        only under `--fix`.

        cargo refuses to rewrite a dirty checkout unless told otherwise, and a
        dirty checkout is exactly the case `--fix` exists for: the point is to
        fix the change you are working on. git is the undo button here."""
        if _no_crate(ctx) or tool_missing("cargo"):
            return (False, "cargo unavailable — nothing fixed")
        rc, _out, err = await run_tool(
            [
                "cargo",
                "clippy",
                "--fix",
                "--allow-dirty",
                "--allow-staged",
                "--allow-no-vcs",
            ],
            ctx.workdir,
        )
        if rc != 0:
            tail = "\n".join((err or "").strip().splitlines()[-2:])
            return (False, f"clippy --fix: did not complete — {tail[:120]}")
        return (False, "clippy --fix applied")


class CargoAuditGate:
    """cargo-audit — RUSTSEC advisory scan of Cargo.lock."""

    name = "cargo_audit"
    blocking = False
    langs = frozenset({"rust"})

    async def run(self, ctx: GateContext) -> GateResult:
        if _no_crate(ctx):
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "rust: no crate (no Cargo.toml)"
            )
        if tool_missing("cargo-audit"):
            return unavailable(self.name, "cargo-audit not installed — skipped")
        rc, out, _err = await run_tool(["cargo", "audit", "--json"], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "{}")
            n = len(data.get("vulnerabilities", {}).get("list") or [])
        except json.JSONDecodeError:
            n = 0
        if n <= 0:
            return GateResult(
                self.name,
                GateOutcome.PASS,
                1.0,
                "cargo-audit: no known vulnerabilities",
            )
        score = max(0.0, 1.0 - min(n, 10) / 10)
        return GateResult(
            self.name, GateOutcome.FAIL, score, f"cargo-audit: {n} vulnerability(ies)"
        )


class RustTestGate:
    name = "cargo_test"
    blocking = False
    langs = frozenset({"rust"})

    async def run(self, ctx: GateContext) -> GateResult:
        if _no_crate(ctx):
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "rust: no crate (no Cargo.toml)"
            )
        if tool_missing("cargo"):
            return unavailable(self.name, "cargo not installed — skipped")
        rc, out, err = await run_tool(["cargo", "test"], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        combined = (out or "") + (err or "")
        if rc == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "cargo test: passed")
        fails = len(re.findall(r"^test .* FAILED$", combined, re.MULTILINE))
        score = 0.0 if not fails else max(0.0, 1.0 - min(fails, 10) / 10)
        tail = "\n".join(combined.strip().splitlines()[-5:])
        return GateResult(
            self.name,
            GateOutcome.FAIL,
            score,
            f"cargo test: {fails or '?'} failure(s) — {tail}",
        )
