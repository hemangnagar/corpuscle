"""Content hashing and Merkle construction.

Every document is identified by SHA-256 of its original bytes. The corpus version
is identified by a Merkle root over the sorted set of document hashes, so the root
is order-independent and any single document's membership can be proven with a
short sibling path instead of the whole corpus.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass

HASH_ALG = "sha256"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pair(a: str, b: str) -> str:
    return hashlib.sha256(bytes.fromhex(a) + bytes.fromhex(b)).hexdigest()


def _levels(leaves: list[str]) -> list[list[str]]:
    """All levels bottom-up. Odd nodes are promoted unchanged (no duplication)."""
    if not leaves:
        return [[hashlib.sha256(b"").hexdigest()]]
    level = sorted(set(leaves))
    levels = [level]
    while len(level) > 1:
        nxt = [_pair(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
               for i in range(0, len(level), 2)]
        levels.append(nxt)
        level = nxt
    return levels


def merkle_root(leaves: list[str]) -> str:
    return _levels(leaves)[-1][0]


@dataclass(frozen=True)
class Proof:
    leaf: str
    path: tuple[tuple[str, str], ...]  # (sibling_hash, "L"|"R")

    def verify(self, root: str) -> bool:
        h = self.leaf
        for sib, side in self.path:
            h = _pair(sib, h) if side == "L" else _pair(h, sib)
        return h == root


def merkle_proof(leaves: list[str], leaf: str) -> Proof:
    levels = _levels(leaves)
    idx = levels[0].index(leaf)
    path = []
    for level in levels[:-1]:
        if idx % 2 == 0:
            if idx + 1 < len(level):
                path.append((level[idx + 1], "R"))
        else:
            path.append((level[idx - 1], "L"))
        idx //= 2
    return Proof(leaf, tuple(path))
