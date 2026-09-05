"""Java / Kotlin gates: compile, checkstyle, ktlint, test.

These need the project's own build tool on the host — Maven or Gradle, whichever
the tree declares — not the gandalf-tools image, and they run in the directory
holding the manifest rather than at the repo root, so a service in a subdirectory
of a monorepo is still built the way its own build file says.

There is no Java-specific dependency-audit gate here on purpose: Maven and Gradle
ship no vulnerability check of their own, and the generic `osv_scanner` and
`trivy` gates already read `pom.xml` / `gradle.lockfile`. Adding OWASP
dependency-check would mean a plugin the repo has not asked for and an NVD
download per run.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from gandalf.base import GateContext, GateResult
from gandalf.gates._toolchain import (
    ToolchainGate,
    counted,
    exit_code,
    project_dir,
    tail,
)
from gandalf.plugins import (
    run_tool,
    timeout_result,
    tool_missing,
    unavailable,
)

_MARKERS = ("pom.xml", "build.gradle", "build.gradle.kts")


@dataclass(frozen=True)
class BuildTool:
    """How to invoke this project's build tool, and what has to be installed."""

    binary: str
    argv: tuple[str, ...]
    kind: str  # "maven" | "gradle"


def build_tool(root: str) -> BuildTool | None:
    """Maven or Gradle for the project at `root`.

    The wrapper wins over a host `gradle`: a Gradle build is only reproducible on
    the version its wrapper pins, and a repo shipping `gradlew` has said which
    version that is.
    """
    p = Path(root)
    if (p / "pom.xml").is_file():
        return BuildTool("mvn", ("mvn", "-B", "-q"), "maven")
    for wrapper in ("gradlew", "gradlew.bat"):
        w = p / wrapper
        if w.is_file():
            return BuildTool(str(w), (str(w), "-q", "--console=plain"), "gradle")
    if (p / "build.gradle").is_file() or (p / "build.gradle.kts").is_file():
        return BuildTool("gradle", ("gradle", "-q", "--console=plain"), "gradle")
    return None


# Maven prints one of these per failing test; Gradle only summarises, so a Gradle
# failure scores as "some" rather than a count. Either way the tail carries the
# summary line the developer actually reads.
_MVN_FAILURE = r"^\[ERROR\]\s+\S+\.\S+(?::\d+)?\s"


class JavaBuildGate(ToolchainGate):
    """`mvn compile` / `gradle classes` — does the tree still build. Blocking."""

    name = "java_build"
    blocking = True
    ecosystem = "java"
    langs = frozenset({"java", "kotlin"})
    markers = _MARKERS

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        tool = build_tool(root)
        if tool is None or tool_missing(tool.binary):
            return self.missing(tool.binary if tool else "maven/gradle")
        goal = "compile" if tool.kind == "maven" else "classes"
        return await exit_code(
            self.name,
            [*tool.argv, goal],
            root,
            ok=f"{tool.kind}: compiles",
            bad=f"{tool.kind}: does not compile",
        )


class CheckstyleGate(ToolchainGate):
    """Checkstyle — the standard Java style/lint checker.

    Configuration is the repo's own when it ships one, since a project's
    checkstyle.xml is the definition of what "clean" means there. Only when
    there is none does this fall back to the bundled Google style, overridable
    with GANDALF_CHECKSTYLE_CONFIG.
    """

    name = "checkstyle"
    ecosystem = "java"
    langs = frozenset({"java"})
    markers = (*_MARKERS, "*.java")
    binary = "checkstyle"

    def _config(self, root: str) -> str:
        for rel in ("checkstyle.xml", "config/checkstyle/checkstyle.xml"):
            if (Path(root) / rel).is_file():
                return rel
        return os.environ.get("GANDALF_CHECKSTYLE_CONFIG", "/google_checks.xml")

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        src = Path(root) / "src"
        target = "src" if src.is_dir() else "."
        rc, out, err = await run_tool(["checkstyle", "-c", self._config(root), target], root)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        combined = (out or "") + (err or "")
        # A bad config, a missing style file: checkstyle exits non-zero with no
        # violations to show. That is the tool failing, not the code.
        lines = [ln for ln in combined.splitlines() if ln.startswith(("[WARN]", "[ERROR]"))]
        if rc != 0 and not lines:
            return unavailable(self.name, f"checkstyle: did not run — {tail(combined, 2)}")
        return counted(
            self.name,
            len(lines),
            "checkstyle",
            [{"message": ln} for ln in lines[:50]],
        )


class KtlintGate(ToolchainGate):
    """ktlint — the standard Kotlin linter/formatter check."""

    name = "ktlint"
    ecosystem = "kotlin"
    langs = frozenset({"kotlin"})
    markers = ("*.kt", "*.kts")
    binary = "ktlint"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        rc, out, _err = await run_tool(["ktlint", "--reporter=json", "--relative"], root)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            report = json.loads(out or "[]")
        except json.JSONDecodeError:
            return unavailable(self.name, "ktlint: unparsable output")
        findings = [
            {
                "file": entry.get("file", ""),
                "line": e.get("line", 0),
                "column": e.get("column", 0),
                "rule": e.get("rule", ""),
                "message": e.get("message", ""),
            }
            for entry in report
            for e in entry.get("errors") or []
        ]
        return counted(self.name, len(findings), "ktlint", findings[:50])

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """`ktlint --format` — rewrites what its rules can fix. Only under `--fix`."""
        root = project_dir(ctx, self.markers)
        if root is None or tool_missing("ktlint"):
            return (False, "ktlint unavailable — nothing fixed")
        await run_tool(["ktlint", "--format", "--relative"], root)
        return (False, "ktlint --format applied")


class JavaTestGate(ToolchainGate):
    name = "java_test"
    ecosystem = "java"
    langs = frozenset({"java", "kotlin"})
    markers = _MARKERS

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        tool = build_tool(root)
        if tool is None or tool_missing(tool.binary):
            return self.missing(tool.binary if tool else "maven/gradle")
        return await exit_code(
            self.name,
            [*tool.argv, "test"],
            root,
            ok=f"{tool.kind} test: passed",
            bad=f"{tool.kind} test: failed",
            fail_re=_MVN_FAILURE if tool.kind == "maven" else "",
        )
