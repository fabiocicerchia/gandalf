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

from . import console, debug
from .base import Gate
from .ignores import (  # noqa: F401 — the gate-facing import surface
    _scan_targets,
    ignore_patterns,
    is_ignored,
    scannable_files,
    set_extra_ignores,
    tracked_files,
)
from .outcomes import (  # noqa: F401 — the gate-facing import surface
    carry_over,
    did_not_run,
    missing_result,
    timeout_result,
    unavailable,
)
from .toolrun import (  # noqa: F401 — the gate-facing import surface
    _TIMEOUT_RC,
    GATE_TIMEOUT,
    IMAGE_TOOLS,
    SUBPROCESS_TIMEOUT_SECONDS,
    TOOLS_IMAGE,
    _tools_image_available,
    communicate,
    reset_tool_sources,
    run_tool,
    tool_missing,
    tool_sources,
    tool_version,
    tool_versions,
    tools_image_id,
)


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
