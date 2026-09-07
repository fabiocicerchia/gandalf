"""Plugin discovery, and the import surface every gate is written against.

A gate is any class exposing `name`, `blocking`, and `async run(ctx)`. Drop a
`.py` file exporting such a class into gandalf/gates/ (or any dir on
GANDALF_GATES_PATH) and it's picked up — no registry to edit. That's the whole
extension mechanism.

The helpers a gate imports from here live in three modules of their own —
`toolrun` (resolve a tool, run it, kill it), `ignores` (what a gate may look at)
and `outcomes` (the "no signal" results) — and are re-exported below because
`from gandalf.plugins import run_tool` is the documented spelling that
third-party gates are written against.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol

from . import console, debug
from .base import Gate
from .ignores import ignore_patterns as ignore_patterns
from .ignores import is_ignored as is_ignored

# The gate-facing import surface: `X as X` is how a re-export is spelled, so a
# checker does not read it as an unused import.
from .ignores import scan_targets as scan_targets
from .ignores import scannable_files as scannable_files
from .ignores import set_extra_ignores as set_extra_ignores
from .ignores import tracked_files as tracked_files
from .outcomes import carry_over as carry_over
from .outcomes import did_not_run as did_not_run
from .outcomes import mark as mark
from .outcomes import meta as meta
from .outcomes import missing_result as missing_result
from .outcomes import timeout_result as timeout_result
from .outcomes import unavailable as unavailable
from .toolrun import GATE_TIMEOUT as GATE_TIMEOUT
from .toolrun import IMAGE_TOOLS as IMAGE_TOOLS
from .toolrun import SUBPROCESS_TIMEOUT_SECONDS as SUBPROCESS_TIMEOUT_SECONDS
from .toolrun import TIMEOUT_RC as TIMEOUT_RC
from .toolrun import TOOLS_IMAGE as TOOLS_IMAGE
from .toolrun import communicate as communicate
from .toolrun import reset_tool_sources as reset_tool_sources
from .toolrun import run_tool as run_tool
from .toolrun import tool_missing as tool_missing
from .toolrun import tool_sources as tool_sources
from .toolrun import tool_version as tool_version
from .toolrun import tool_versions as tool_versions
from .toolrun import tools_image_available as tools_image_available
from .toolrun import tools_image_id as tools_image_id


class NamedGate(Protocol):
    """A gate seen only by its name.

    The cache keys on it and the fixer pass reports under it; neither runs the
    gate, so neither should demand the whole `Gate` protocol — a fix-only gate
    has no `run`, and a test double has no reason to grow one.
    """

    name: str


def gate_langs(gate: Gate) -> set[str]:
    """The languages a gate declares, or an empty set when it declares none.

    `langs` is optional rather than part of the `Gate` protocol — a gate that
    applies to any tree simply omits it — so it is read here instead of being
    required of every gate file.
    """
    return {str(lang) for lang in getattr(gate, "langs", None) or ()}


def _gate_dirs() -> list[Path]:
    """Every directory gates are discovered from.

    The built-in directory first, then anything on GANDALF_GATES_PATH — which
    is how a project adds its own gate without vendoring gandalf.

    GANDALF_GATES_PATH is a trust boundary: every `.py` in those directories is
    imported, and module-level code runs at import time, before anything checks
    whether the file defines a gate at all. Whoever can set that variable can
    execute code as whatever user gandalf runs as. See docs/configuration.md.
    """
    dirs = [Path(__file__).parent / "gates"]
    for extra in filter(None, os.environ.get("GANDALF_GATES_PATH", "").split(os.pathsep)):
        dirs.append(Path(extra))
    return [d for d in dirs if d.is_dir()]


def _load_module(path: Path) -> ModuleType:
    """Import one gate file by path, under a namespaced module name.

    Namespaced so two gate directories can hold files with the same basename
    without the second silently shadowing the first.
    """
    spec = importlib.util.spec_from_file_location(f"gandalf_gate_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load gate module from {path}")
    mod = importlib.util.module_from_spec(spec)
    # Registered before it executes, the way importlib itself does it: several
    # stdlib decorators (@dataclass, Enum, NamedTuple) look their own class's
    # module up in sys.modules while the class body is being built, and a gate
    # file using one of them dies on import if it is not there.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _gates_in(mod: ModuleType) -> list[Gate]:
    """Every Gate-shaped class the module itself defines, instantiated.

    Classes it merely imported (GateResult, a shared base) are skipped — they
    belong to whoever defined them.
    """
    found: list[Gate] = []
    for _, obj in inspect.getmembers(mod, inspect.isclass):
        if obj.__module__ != mod.__name__:
            continue
        if not all(hasattr(obj, attr) for attr in ("name", "blocking", "run")):
            continue
        inst = obj()
        if isinstance(inst, Gate):
            found.append(inst)
    return found


def discover_gates() -> list[Gate]:
    """Instantiate every Gate-shaped class found in the plugin dirs."""
    gates: dict[str, Gate] = {}
    builtin = _gate_dirs()[0]
    for d in _gate_dirs():
        external = d != builtin
        if external:
            debug.log(f"loading external gates from {d} (GANDALF_GATES_PATH)")
        for path in sorted(d.glob("*.py")):
            if path.name.startswith("_"):
                continue
            for inst in _gates_in(_load_module(path)):
                if external and inst.name in gates:
                    # A plugin replacing a built-in is legitimate — it is how you
                    # swap a scanner — but it must never be silent: a gate named
                    # `gitleaks` that reports a clean pass is otherwise
                    # indistinguishable from the real one in every output.
                    console.err(f"gandalf: gate '{inst.name}' overridden by {path} (GANDALF_GATES_PATH)")
                gates[inst.name] = inst  # name wins on collision → override built-ins
    return list(gates.values())
