"""Integrity family: did the bytes survive the trip, and is the text whole?

Corpus-level rates, one flag each on the record:
  empty            no extractable text after parsing (usually a failed parse, not a short document)
  near_empty       under 20 tokens (same estimate the volume family uses)
  truncated        non-empty, not near-empty, and the last character is not terminal punctuation
                   once trailing markup and a trailing banner line are set aside
  mojibake         ftfy.fix_encoding changes the text: fixable encoding damage
  control_chars    a Cc control character outside whitespace, or U+FFFD, the replacement character
  markup_residue   an HTML/XML tag or entity survived parsing
  large            size_bytes over the threshold (default 10 MiB)

Document-level shares, reported as distributions:
  int.boilerplate_share     lines a simple boilerplate filter would remove: under four words, or
                            matching copyright, rights-reserved, unsubscribe, cookie, privacy, terms,
                            "page N of M" or a confidentiality notice. 0 for a single-line document.
  int.intra_doc_repetition  share of non-empty lines that repeat an earlier line (normalized)
  int.ngram_repetition      Gopher-style: share of word characters inside a 2-, 3- or 4-gram that
                            occurs more than once; the maximum over n

Every rule here is a cheap, explainable heuristic, and its method_version is the contract: a
better heuristic is a new version with a re-baseline, never a silent change.
"""
from __future__ import annotations
import re
import unicodedata
from importlib.metadata import version as pkg_version
from typing import Iterable

import ftfy

from ..markings import parse_banner
from . import Result, register
from .volume import estimate_tokens

NEAR_EMPTY_TOKENS = 20
LARGE_BYTES = 10 * 1024 * 1024
TERMINAL = set(".!?…:;\"')]}»")
_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s[^<>]*)?/?>")
_ENTITY = re.compile(r"&(?:[a-z]{2,8}|#\d{2,5}|#x[0-9a-fA-F]{2,4});")
_BOILERPLATE = re.compile(r"(?i)(©|\(c\)\s*\d{4}|copyright|all rights reserved|unsubscribe|cookie|privacy policy|"
                          r"terms of (?:use|service)|page \d+ of \d+|confidential(?:ity)? notice|do not (?:forward|distribute))")
_WORD = re.compile(r"\w+", re.UNICODE)


def _flag(record: dict, flag: str) -> None:
    flags = record.setdefault("flags", [])
    if flag not in flags:
        flags.append(flag)
        flags.sort()


def has_control_chars(text: str) -> bool:
    return any((unicodedata.category(c) == "Cc" and c not in "\t\n\r\x0b\x0c") or c == "�" for c in text)


def has_markup(text: str) -> bool:
    return bool(_TAG.search(text) or _ENTITY.search(text))


def is_mojibake(text: str) -> bool:
    return ftfy.fix_encoding(text) != text


def boilerplate_share(text: str) -> float:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return 0.0
    removed = sum(1 for l in lines if len(_WORD.findall(l)) < 4 or _BOILERPLATE.search(l))
    return round(removed / len(lines), 6)


def intra_doc_repetition(text: str) -> float:
    lines = [" ".join(l.lower().split()) for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return 0.0
    return round((len(lines) - len(set(lines))) / len(lines), 6)


def ngram_repetition(text: str) -> float:
    words = [w.lower() for w in _WORD.findall(text)]
    total = sum(len(w) for w in words)
    if total == 0:
        return 0.0
    worst = 0.0
    for n in (2, 3, 4):
        if len(words) < n:
            break
        grams = [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]
        counts: dict[tuple, int] = {}
        for g in grams:
            counts[g] = counts.get(g, 0) + 1
        covered = [False] * len(words)
        for i, g in enumerate(grams):
            if counts[g] > 1:
                for j in range(i, i + n):
                    covered[j] = True
        worst = max(worst, sum(len(w) for w, c in zip(words, covered) if c) / total)
    return round(worst, 6)


class IntegrityAnalyzer:
    name = "integrity"
    version = "0.1.0"
    produces = ("int.empty_count", "int.empty_rate", "int.near_empty_rate", "int.truncation_rate", "int.mojibake_rate",
                "int.control_char_rate", "int.markup_residue_rate", "int.large_count", "int.large_rate",
                "int.boilerplate_share", "int.intra_doc_repetition", "int.ngram_repetition")

    def __init__(self, large_bytes: int = LARGE_BYTES):
        self.large_bytes = large_bytes
        self.pins = {"ftfy": pkg_version("ftfy"), "integrity": f"near_empty<{NEAR_EMPTY_TOKENS}tok,large>{large_bytes}B"}

    def per_document(self, record: dict) -> dict:
        text = record.get("text", "")
        stripped = text.strip()
        tokens = estimate_tokens(text)
        out = {
            "int.boilerplate_share": boilerplate_share(text),
            "int.intra_doc_repetition": intra_doc_repetition(text),
            "int.ngram_repetition": ngram_repetition(text),
            "_int.flags": [],
        }
        f = out["_int.flags"]
        if not stripped:
            f.append("empty")
        if tokens < NEAR_EMPTY_TOKENS:
            f.append("near_empty")
        else:
            lines = [l for l in stripped.splitlines() if l.strip()]
            while lines and parse_banner(lines[-1]):
                lines.pop()
            tail = _ENTITY.sub("", _TAG.sub("", "\n".join(lines))).rstrip()
            if tail and tail[-1] not in TERMINAL:
                f.append("truncated")
        if stripped and is_mojibake(text):
            f.append("mojibake")
        if has_control_chars(text):
            f.append("control_chars")
        if has_markup(text):
            f.append("markup_residue")
        if record.get("envelope", {}).get("size_bytes", 0) > self.large_bytes:
            f.append("large")
        return out

    def corpus(self, records: Iterable[dict]) -> list[Result]:
        records = list(records)
        n = len(records)
        counts = {k: 0 for k in ("empty", "near_empty", "truncated", "mojibake", "control_chars", "markup_residue", "large")}
        shares = {"int.boilerplate_share": [], "int.intra_doc_repetition": [], "int.ngram_repetition": []}
        for r in records:
            m = r.get("metrics", {})
            for flag in m.get("_int.flags", []):
                counts[flag] += 1
                _flag(r, flag)
            for k in shares:
                shares[k].append(m.get(k, 0.0))
        rate = lambda c: round(c / n, 6) if n else 0.0

        def dist(values):
            if not values:
                return None
            v = sorted(values)
            q = lambda p: v[min(len(v) - 1, int(p * (len(v) - 1)))]
            return {"min": v[0], "p50": q(0.5), "p95": q(0.95), "max": v[-1], "mean": round(sum(v) / len(v), 6)}

        return [
            Result("int.empty_count", self.version, counts["empty"], unit="docs"),
            Result("int.empty_rate", self.version, rate(counts["empty"]), unit="fraction"),
            Result("int.near_empty_rate", self.version, rate(counts["near_empty"]), unit="fraction"),
            Result("int.truncation_rate", self.version, rate(counts["truncated"]), unit="fraction"),
            Result("int.mojibake_rate", self.version, rate(counts["mojibake"]), unit="fraction"),
            Result("int.control_char_rate", self.version, rate(counts["control_chars"]), unit="fraction"),
            Result("int.markup_residue_rate", self.version, rate(counts["markup_residue"]), unit="fraction"),
            Result("int.large_count", self.version, counts["large"], unit="docs"),
            Result("int.large_rate", self.version, rate(counts["large"]), unit="fraction"),
            Result("int.boilerplate_share", self.version, None, unit="fraction", distribution=dist(shares["int.boilerplate_share"])),
            Result("int.intra_doc_repetition", self.version, None, unit="fraction", distribution=dist(shares["int.intra_doc_repetition"])),
            Result("int.ngram_repetition", self.version, None, unit="fraction", distribution=dist(shares["int.ngram_repetition"])),
        ]


register(IntegrityAnalyzer())
