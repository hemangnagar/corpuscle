"""Duplication family: exact and near duplicates.

Exact: records whose doc_hash appears more than once. Free, because records are keyed by
content hash; byte-identical documents at different locators already share one.

Near: MinHash over 5-word shingles, 128 permutations. LSH is only the candidate net: it is
indexed below the configured threshold and weighted for recall, because banding at the
threshold itself misses pairs that sit just above it. Each candidate is confirmed by the
estimated Jaccard against the real threshold (catalog default 0.8); clusters by union-find. One representative per doc_hash goes into the index; every record whose content
sits in a cluster of two or more distinct doc_hashes is a near duplicate. Documents with fewer
than five words have no shingles and cannot be near duplicates of anything.

The per-document step emits the MinHash as a scratch value (key prefixed "_"); the runner keeps
scratch in memory for the corpus step and strips it before records are written, so the same
code runs under mapPartitions with a corpus-level join at the end.

Flags written to records: exact_duplicate, near_duplicate. The finding gate reads them as evidence.
"""
from __future__ import annotations
import re
from collections import Counter, defaultdict
from importlib.metadata import version as pkg_version
from typing import Iterable

from datasketch import MinHash, MinHashLSH

from . import Result, register

NUM_PERM = 128
SHINGLE = 5
THRESHOLD = 0.8
INDEX_MARGIN = 0.2          # LSH indexes at threshold - margin; confirmation uses threshold
INDEX_WEIGHTS = (0.1, 0.9)  # (false positive, false negative): pay in candidates, not in recall
SCRATCH = "_dup.minhash"
_WORD = re.compile(r"\w+", re.UNICODE)


def shingles(text: str, k: int = SHINGLE) -> list[bytes]:
    words = _WORD.findall(text.lower())
    return [" ".join(words[i:i + k]).encode("utf-8") for i in range(len(words) - k + 1)]


def minhash(text: str) -> MinHash | None:
    sh = shingles(text)
    if not sh:
        return None
    m = MinHash(num_perm=NUM_PERM)
    for s in sh:
        m.update(s)
    return m


class DuplicationAnalyzer:
    name = "duplication"
    version = "0.1.0"
    produces = ("dup.exact_count", "dup.exact_rate", "dup.near_count", "dup.near_rate")

    def __init__(self, threshold: float = THRESHOLD):
        self.threshold = threshold
        self.index_threshold = round(max(0.1, threshold - INDEX_MARGIN), 3)
        self.pins = {"datasketch": pkg_version("datasketch"),
                     "minhash": f"num_perm={NUM_PERM},shingle={SHINGLE}-word,threshold={threshold},"
                                f"lsh_index={self.index_threshold},lsh_weights={INDEX_WEIGHTS[0]}/{INDEX_WEIGHTS[1]}"}

    def per_document(self, record: dict) -> dict:
        m = minhash(record.get("text", ""))
        return {SCRATCH: m.hashvalues.tolist()} if m is not None else {}

    def corpus(self, records: Iterable[dict]) -> list[Result]:
        records = list(records)
        n = len(records)

        counts = Counter(r["doc_hash"] for r in records)
        exact = 0
        for r in records:
            if counts[r["doc_hash"]] > 1:
                exact += 1
                _flag(r, "exact_duplicate")

        reps: dict[str, MinHash] = {}
        for r in records:
            h = r["doc_hash"]
            hv = r.get("metrics", {}).get(SCRATCH)
            if hv is not None and h not in reps:
                reps[h] = MinHash(num_perm=NUM_PERM, hashvalues=hv)

        parent = {h: h for h in reps}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        lsh = MinHashLSH(threshold=self.index_threshold, num_perm=NUM_PERM, weights=INDEX_WEIGHTS)
        for h in sorted(reps):
            lsh.insert(h, reps[h])
        for h in sorted(reps):
            for other in lsh.query(reps[h]):
                if other != h and reps[h].jaccard(reps[other]) >= self.threshold:
                    parent[find(h)] = find(other)

        members = defaultdict(set)
        for h in reps:
            members[find(h)].add(h)
        near_hashes = {h for h in reps if len(members[find(h)]) > 1}
        near = 0
        for r in records:
            if r["doc_hash"] in near_hashes:
                near += 1
                _flag(r, "near_duplicate")

        rate = lambda c: round(c / n, 6) if n else 0.0
        return [
            Result("dup.exact_count", self.version, exact, unit="docs"),
            Result("dup.exact_rate", self.version, rate(exact), unit="fraction"),
            Result("dup.near_count", self.version, near, unit="docs"),
            Result("dup.near_rate", self.version, rate(near), unit="fraction"),
        ]


def _flag(record: dict, flag: str) -> None:
    flags = record.setdefault("flags", [])
    if flag not in flags:
        flags.append(flag)
        flags.sort()


register(DuplicationAnalyzer())
