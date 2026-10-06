"""Plain-text banner and portion-mark parser.

Scope: the banner-and-portion convention used on US government documents in plain text, in
the uppercase forms that appear on a page. A banner is a line that is nothing but a marking:

    UNCLASSIFIED            SECRET//NOFORN           TOP SECRET//SI//REL TO USA, FVEY
    UNCLASSIFIED//FOUO      CUI//SP-PRVCY            CONFIDENTIAL

A portion mark opens a paragraph or line: (U), (CUI), (C), (S), (TS), (S//NF), (U//FOUO).

Levels are ordered U < CUI < C < S < TS for ceiling purposes. CUI is not a classification
level; it is placed above U so that a corpus whose ceiling is U is breached by CUI content,
which is the question an authorizing official asks. Nothing here parses ISM XML metadata;
that is the Phase 4 parser, and it will feed the same parsed shape.

The parser never stores marked text: it returns levels, counts and booleans. Redaction residue
means a placeholder left by a redaction tool ([REDACTED], (b)(6), block characters, X-runs) or
a banner-shaped marking appearing inside a line of body text, where it was pasted rather than
applied.
"""
from __future__ import annotations
import re
from collections import Counter

LEVELS = {"U": 0, "CUI": 1, "C": 2, "S": 3, "TS": 4}
_LEVEL_WORDS = {"UNCLASSIFIED": "U", "CONTROLLED UNCLASSIFIED INFORMATION": "CUI", "CUI": "CUI",
                "CONFIDENTIAL": "C", "SECRET": "S", "TOP SECRET": "TS"}
_WORDS = "TOP SECRET|SECRET|CONFIDENTIAL|UNCLASSIFIED|CONTROLLED UNCLASSIFIED INFORMATION|CUI"
_BANNER_LINE = re.compile(rf"^\s*({_WORDS})(//[A-Z0-9][A-Z0-9 ,/\-]*)?\s*$")
_PORTION = re.compile(r"^\s*(?:[-*•]\s*|\d+[.)]\s*)?\((U|CUI|C|S|TS)(//[A-Z0-9][A-Z0-9 ,/\-]*?)?\)")
_INLINE_MARKING = re.compile(rf"\b({_WORDS})//[A-Z][A-Z0-9 ,/\-]*")
_REDACTION = re.compile(r"\[(?:REDACTED|DELETED|WITHHELD|REMOVED)\]|\(b\)\(\d\)(?:\([A-Za-z]\))?|[█■]{3,}|\bX{6,}\b", re.IGNORECASE)


def parse_banner(line: str) -> dict | None:
    m = _BANNER_LINE.match(line)
    if not m:
        return None
    word, controls = m.group(1), (m.group(2) or "")
    parts = [p.strip() for p in controls.split("//") if p.strip()]
    return {"level": _LEVEL_WORDS[word], "controls": parts, "raw": line.strip()}


def parse(text: str, source_markings: list[str] | None = None) -> dict:
    """Return the parsed shape stored in record.markings_parsed. Counts and levels only."""
    banners: list[dict] = []
    portions: Counter = Counter()
    residue = False
    for raw in text.splitlines():
        b = parse_banner(raw)
        if b:
            if b["raw"] not in {x["raw"] for x in banners}:
                banners.append(b)
            continue
        p = _PORTION.match(raw)
        if p:
            portions[p.group(1)] += 1
        if _REDACTION.search(raw) or _INLINE_MARKING.search(raw):
            residue = True
    for s in source_markings or []:
        b = parse_banner(s)
        if b and b["raw"] not in {x["raw"] for x in banners}:
            banners.append({**b, "from": "source"})

    banner_levels = {b["level"] for b in banners}
    banner_max = max(banner_levels, key=LEVELS.get) if banner_levels else None
    portion_max = max(portions, key=LEVELS.get) if portions else None
    doc_max = max([x for x in (banner_max, portion_max) if x], key=LEVELS.get, default=None)
    conflict = (len(banner_levels) > 1) or (banner_max is not None and portion_max is not None and banner_max != portion_max)
    return {
        "banner": banner_max,
        "banners": [b["raw"] for b in banners],
        "controls": sorted({c for b in banners for c in b["controls"]}),
        "portions": dict(sorted(portions.items(), key=lambda kv: LEVELS[kv[0]])),
        "portion_max": portion_max,
        "level": doc_max,
        "marked": doc_max is not None,
        "conflict": conflict,
        "redaction_residue": residue,
    }


def above(level: str | None, ceiling: str | None) -> bool:
    return level is not None and ceiling is not None and LEVELS[level] > LEVELS[ceiling]
