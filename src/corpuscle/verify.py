"""Offline verification. No server, no network: a corpus directory, its bundle, and a public key.

Checks, in order: signature, manifest schema, records hash, records count, Merkle root
against the records, and (when the corpus files are present) every file's hash against
its record — reporting added, removed and changed documents.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

from .envelope import validate
from .hashing import merkle_root, sha256_bytes, sha256_file
from .manifest import BUNDLE_DIR
from .signing import Verifier, open_envelope


@dataclass
class Report:
    ok: bool
    checks: dict = field(default_factory=dict)
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    manifest: dict | None = None

    def __str__(self) -> str:
        lines = [f"{'PASS' if v else 'FAIL'}  {k}" for k, v in self.checks.items()]
        if self.added: lines.append(f"added ({len(self.added)}): " + ", ".join(self.added[:5]))
        if self.removed: lines.append(f"removed ({len(self.removed)}): " + ", ".join(h[:12] for h in self.removed[:5]))
        if self.changed: lines.append(f"changed ({len(self.changed)}): " + ", ".join(self.changed[:5]))
        lines.append("RESULT  " + ("verified" if self.ok else "NOT verified"))
        return "\n".join(lines)


def verify(bundle_root, verifiers: list[Verifier], corpus_dir=None, locator_to_path=None) -> Report:
    b = Path(bundle_root) / BUNDLE_DIR
    rep = Report(ok=False)
    try:
        st = open_envelope(json.loads((b / "manifest.dsse.json").read_text()), verifiers)
        rep.checks["signature"] = True
    except Exception as e:
        rep.checks["signature"] = False
        rep.checks[f"signature error: {e}"] = False
        return rep
    m = st["predicate"]
    rep.manifest = m
    try:
        validate(m, "manifest.schema.json"); rep.checks["manifest schema"] = True
    except Exception:
        rep.checks["manifest schema"] = False

    records_bytes = (b / "records.jsonl").read_bytes()
    rep.checks["records hash"] = sha256_bytes(records_bytes) == m["records_hash"]
    records = [json.loads(l) for l in records_bytes.decode().splitlines() if l.strip()]
    rep.checks["records count"] = len(records) == m["records_count"] == m["corpus"]["document_count"]
    hashes = [r["doc_hash"] for r in records]
    rep.checks["merkle root"] = merkle_root(hashes) == m["corpus"]["merkle_root"]
    rep.checks["statement subject"] = st["subject"][0]["digest"]["sha256"] == m["corpus"]["merkle_root"]

    if corpus_dir is not None:
        corpus_dir = Path(corpus_dir)
        loc = locator_to_path or (lambda locator: corpus_dir / locator)
        expected = [(r["doc_hash"], r["envelope"]["source_locator"]) for r in records]
        seen = set()
        for h, locator in expected:
            p = loc(locator)
            if not p.exists():
                rep.removed.append(h); continue
            seen.add(p.resolve())
            if sha256_file(p) != h:
                rep.changed.append(locator)
        for p in corpus_dir.rglob("*"):
            if p.is_file() and BUNDLE_DIR not in p.parts and p.resolve() not in seen:
                rep.added.append(str(p.relative_to(corpus_dir)))
        rep.checks["corpus files match records"] = not (rep.added or rep.removed or rep.changed)

    rep.ok = all(rep.checks.values())
    return rep
