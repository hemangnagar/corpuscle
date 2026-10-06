"""Provenance family: computed entirely from the envelope captured at ingest.

No text is read. Every metric here answers a question the authorizing official asks that a
model cannot answer about its own corpus: where did this come from, when, through whose hands,
and does the source's own identifier agree with the bytes.

Flags written to records: undated, duplicate_source_id. The finding gate cites them as evidence.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from typing import Iterable

from . import Result, register


def _flag(record: dict, flag: str) -> None:
    flags = record.setdefault("flags", [])
    if flag not in flags:
        flags.append(flag)
        flags.sort()


class ProvenanceAnalyzer:
    name = "provenance"
    version = "0.1.0"
    produces = ("prov.source_histogram", "prov.date_range", "prov.undated_rate", "prov.custody_complete_rate",
                "prov.reliability_histogram", "prov.derived_share", "prov.duplicate_id_count", "prov.duplicate_id_rate")
    pins: dict = {}

    def per_document(self, record: dict) -> dict:
        return {}

    def corpus(self, records: Iterable[dict]) -> list[Result]:
        records = list(records)
        n = len(records)
        rate = lambda c, of=n: round(c / of, 6) if of else 0.0

        sources: dict[str, dict] = defaultdict(lambda: {"docs": 0, "bytes": 0})
        dates, undated, custody, derived, rated = [], 0, 0, 0, Counter()
        by_id: dict[tuple, set] = defaultdict(set)
        with_id = 0
        for r in records:
            e = r["envelope"]
            s = sources[e["source_system"]]
            s["docs"] += 1
            s["bytes"] += e["size_bytes"]
            if e.get("collected_at"):
                dates.append(e["collected_at"])
            else:
                undated += 1
                _flag(r, "undated")
            if e.get("custody"):
                custody += 1
            if e.get("parent_hash"):
                derived += 1
            rel = e.get("reliability") or {}
            if rel:
                rated[f"{rel.get('source', '?')}{rel.get('information', '?')}"] += 1
            if e.get("source_id"):
                with_id += 1
                by_id[(e["source_system"], e["source_id"])].add(r["doc_hash"])

        conflicting = {k for k, hashes in by_id.items() if len(hashes) > 1}
        dup_ids = 0
        for r in records:
            e = r["envelope"]
            if e.get("source_id") and (e["source_system"], e["source_id"]) in conflicting:
                dup_ids += 1
                _flag(r, "duplicate_source_id")

        date_range = {"min": min(dates), "max": max(dates), "dated": len(dates)} if dates else None
        reliability = dict(sorted(rated.items()))
        reliability["unrated"] = n - sum(rated.values())
        return [
            Result("prov.source_histogram", self.version, {k: sources[k] for k in sorted(sources)}),
            Result("prov.date_range", self.version, date_range),
            Result("prov.undated_rate", self.version, rate(undated), unit="fraction"),
            Result("prov.custody_complete_rate", self.version, rate(custody), unit="fraction"),
            Result("prov.reliability_histogram", self.version, reliability),
            Result("prov.derived_share", self.version, rate(derived), unit="fraction"),
            Result("prov.duplicate_id_count", self.version, dup_ids, unit="docs"),
            Result("prov.duplicate_id_rate", self.version, rate(dup_ids, with_id) if with_id else None, unit="fraction"),
        ]


register(ProvenanceAnalyzer())
