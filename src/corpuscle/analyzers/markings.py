"""Compliance family, marking metrics: coverage, banner/portion conflicts, ceiling breaches,
redaction residue. The parser is corpuscle.markings; this analyzer only counts what it returns.

The authorized ceiling is a run parameter (scan --ceiling), recorded in the pins. Without one,
mark.ceiling_breach is undefined and the gate says inconclusive rather than pass: the question
was not asked of this run.

Flags written to records: unmarked, marking_conflict, ceiling_breach, redaction_residue. Flags name
defects; a marked document carries its parse in markings_parsed and no flag.
"""
from __future__ import annotations
from typing import Iterable

from .. import markings as mk
from . import Result, register

PARSER_VERSION = "capco-text/0.1"


def _flag(record: dict, flag: str) -> None:
    flags = record.setdefault("flags", [])
    if flag not in flags:
        flags.append(flag)
        flags.sort()


class MarkingAnalyzer:
    name = "markings"
    version = "0.1.0"
    produces = ("mark.coverage", "mark.conflict_rate", "mark.ceiling_breach", "mark.redaction_residue_rate")

    def __init__(self, ceiling: str | None = None):
        if ceiling is not None and ceiling not in mk.LEVELS:
            raise ValueError(f"ceiling must be one of {', '.join(mk.LEVELS)}; got {ceiling!r}")
        self.ceiling = ceiling
        self.pins = {"markings": f"{PARSER_VERSION},ceiling={ceiling or 'none'}"}

    def with_config(self, **kw) -> "MarkingAnalyzer":
        return MarkingAnalyzer(**kw)

    def per_document(self, record: dict) -> dict:
        parsed = mk.parse(record.get("text", ""), record.get("envelope", {}).get("markings"))
        return {"_mark.parsed": parsed}

    def corpus(self, records: Iterable[dict]) -> list[Result]:
        records = list(records)
        n = len(records)
        marked = conflict = breach = residue = 0
        for r in records:
            p = r.get("metrics", {}).pop("_mark.parsed", None) or mk.parse("")
            r["markings_parsed"] = p
            if p["marked"]:
                marked += 1
            else:
                _flag(r, "unmarked")
            if p["conflict"]:
                conflict += 1
                _flag(r, "marking_conflict")
            if self.ceiling is not None and mk.above(p["level"], self.ceiling):
                breach += 1
                _flag(r, "ceiling_breach")
            if p["redaction_residue"]:
                residue += 1
                _flag(r, "redaction_residue")
        rate = lambda c: round(c / n, 6) if n else 0.0
        return [
            Result("mark.coverage", self.version, rate(marked), unit="fraction"),
            Result("mark.conflict_rate", self.version, rate(conflict), unit="fraction"),
            Result("mark.ceiling_breach", self.version, breach if self.ceiling is not None else None, unit="docs"),
            Result("mark.redaction_residue_rate", self.version, rate(residue), unit="fraction"),
        ]


register(MarkingAnalyzer())
