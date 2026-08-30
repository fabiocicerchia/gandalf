"""C / C++ gates: cmake build, cppcheck, ctest.

C and C++ have no single package manager and no standard test runner, so this
suite is deliberately three gates rather than four: dependency vulnerabilities
for a conan/vcpkg lock file are the generic osv_scanner/trivy gates' job, and
there is no ecosystem-native audit tool to wire up.

The build configures into a throwaway directory outside the worktree, so a scan
never leaves a `build/` behind or disturbs one already there. A configure that
fails is amber, not red: a missing system library says something about the
machine gandalf is running on, while a compile error says something about the
code — a quality gate must not confuse the two.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import (
    ToolchainGate,
    counted,
    exit_code,
    sources,
    tail,
)
from gandalf.plugins import (
    run_tool,
    timeout_result,
    unavailable,
)

_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx")
_SOURCES = tuple(f"*{s}" for s in _SUFFIXES)
_LANGS = frozenset({"c", "cpp"})
# Where a configured tree usually lives, in the order people generate them.
_BUILD_DIRS = ("build", "cmake-build-debug", "cmake-build-release", "out/build")


class CppBuildGate(ToolchainGate):
    """`cmake -B … && cmake --build …` against the project's own CMakeLists.

    Not blocking, unlike the Go and Rust build gates: a C++ build depends on
    system libraries gandalf cannot install, so "it did not build here" is not
    reliable enough to hard-red a change on its own.
    """

    name = "cpp_build"
    ecosystem = "cmake"
    langs = _LANGS
    markers = ("CMakeLists.txt",)
    binary = "cmake"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        out_dir = tempfile.mkdtemp(prefix="gandalf-cmake-")
        try:
            rc, out, err = await run_tool(
                ["cmake", "-S", root, "-B", out_dir, "-DCMAKE_BUILD_TYPE=Debug"], root
            )
            if (to := timeout_result(self.name, rc)) is not None:
                return to
            if rc != 0:
                return unavailable(
                    self.name,
                    f"cmake: configure failed (toolchain or deps) — "
                    f"{tail((out or '') + (err or ''), 3)}",
                )
            return await exit_code(
                self.name,
                ["cmake", "--build", out_dir, "--parallel"],
                root,
                ok="cmake: compiles",
                bad="cmake: does not compile",
            )
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


# `--template` output: path:line:severity:id:message
_HIT = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<sev>\w+):(?P<id>\w+):(?P<msg>.*)$"
)


class CppcheckGate(ToolchainGate):
    """cppcheck — static analysis that needs no compile database or build."""

    name = "cppcheck"
    ecosystem = "c/c++"
    langs = _LANGS
    markers = _SOURCES
    binary = "cppcheck"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        targets = sources(ctx, *_SUFFIXES) or ["."]
        rc, out, err = await run_tool(
            [
                "cppcheck",
                "--enable=warning,performance,portability",
                "--inline-suppr",
                "--quiet",
                "--template={file}:{line}:{severity}:{id}:{message}",
                *targets,
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        # cppcheck reports on stderr and exits 0 unless it could not run at all.
        findings = []
        for line in ((err or "") + (out or "")).splitlines():
            m = _HIT.match(line.strip())
            if m:
                findings.append(
                    {
                        "file": m["file"],
                        "line": int(m["line"]),
                        "rule": m["id"],
                        "severity": m["sev"],
                        "message": m["msg"].strip(),
                    }
                )
        if rc != 0 and not findings:
            return unavailable(
                self.name,
                f"cppcheck: did not run — {tail((err or '') + (out or ''), 2)}",
            )
        return counted(self.name, len(findings), "cppcheck", findings[:50])


class CtestGate(ToolchainGate):
    """`ctest` in a build tree that already exists.

    Nothing is configured or compiled here: cpp_build throws its tree away, and
    building a second time to run the tests would double the slowest gate in the
    suite. When CI (or the developer) has a build directory, the tests run;
    otherwise there is nothing to run and that is a pass, not a warning.
    """

    name = "cpp_test"
    ecosystem = "cmake"
    langs = _LANGS
    markers = ("CMakeLists.txt",)
    binary = "ctest"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        for rel in _BUILD_DIRS:
            tree = Path(root) / rel
            if (tree / "CTestTestfile.cmake").is_file():
                return await exit_code(
                    self.name,
                    ["ctest", "--test-dir", str(tree), "--output-on-failure"],
                    root,
                    ok="ctest: passed",
                    bad="ctest: failed",
                    fail_re=r"^\s*\d+ - .*\(Failed\)",
                )
        return GateResult(
            self.name, GateOutcome.PASS, 1.0, "ctest: no configured build tree"
        )
