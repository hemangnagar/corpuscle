"""Analyzer contract.

An analyzer declares the metric IDs it produces and computes them from canonical
document records. Two entry points so the same analyzer runs locally and under
PySpark (mapPartitions for per_document, a reduce for corpus):

    per_document(record) -> dict[metric_id, value]     pure, no I/O
    corpus(records_iter) -> list[Result]               may aggregate per-document values

Every analyzer pins the detector versions it depends on; the runner records them
in manifest.run.pins so a result can be regenerated a year later.

Scratch values: a per_document key prefixed "_" (a MinHash signature, say) is kept
in memory for the corpus step and stripped before records are written. corpus() may
append to a record's "flags" so the finding gate can cite the documents as evidence.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, Protocol


@dataclass
class Result:
    metric_id: str
    method_version: str
    value: object
    unit: str | None = None
    scope: str = "all"
    distribution: dict | None = None
    sample: dict | None = None
    confidence: float | None = None

    def to_json(self) -> dict:
        d = {"metric_id": self.metric_id, "method_version": self.method_version, "value": self.value}
        for k in ("unit", "scope", "distribution", "sample", "confidence"):
            v = getattr(self, k)
            if v is not None and not (k == "scope" and v == "all"):
                d[k] = v
        return d


class Analyzer(Protocol):
    name: str
    version: str
    produces: tuple[str, ...]
    pins: dict[str, str]

    def per_document(self, record: dict) -> dict: ...
    def corpus(self, records: Iterable[dict]) -> list[Result]: ...


REGISTRY: dict[str, "Analyzer"] = {}


def register(a: "Analyzer") -> "Analyzer":
    REGISTRY[a.name] = a
    return a
