"""--stream: one NDJSON line per gate on stdout, as it completes."""

from __future__ import annotations

import dataclasses
import json

from . import findings as gfindings
from . import plugins, report


class GateStream:
    """One NDJSON line per gate on stdout, as it completes.

    Without this a consumer learns nothing until the final report is written, so
    an editor pane sits empty for the whole run. Lines are emitted in completion
    order and the aggregate (verdict, composite score) still comes only from the
    final report — a gate result on its own can't produce one.

    Findings are passed through the suppressor first so a baselined finding
    doesn't flash up and then vanish when the report lands. Severity weighting is
    not applied, so a streamed `score` is preliminary; the report is the record.
    """

    def __init__(self, total: int, scope: str, sup, workdir: str = ""):
        self.total = total
        self.n = 0
        self.sup = sup
        self.workdir = workdir
        self._write({"event": "start", "scope": scope, "gates": total})

    def gate(self, r) -> None:
        self.n += 1
        shown = self.sup.apply(r) if self.sup.active else r
        self._write(
            {
                "event": "gate",
                "index": self.n,
                "total": self.total,
                **dataclasses.asdict(shown),
                "findings": gfindings.annotate_all(shown.findings, self.workdir),
                "category": report.category_of(r),
                "duration": getattr(r, "_duration", None),
                "blocking": getattr(r, "_blocking", False),
                "unavailable": plugins.did_not_run(r),
            }
        )

    @staticmethod
    def _write(obj: dict) -> None:
        # flush: the point is to be read while the process is still running.
        print(json.dumps(obj, default=str), flush=True)
