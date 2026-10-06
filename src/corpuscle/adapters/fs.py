"""Filesystem adapter, with an optional sidecar provenance file.

A directory of files knows nothing about where its files came from: the envelope records the
path, size and hash and the fact that the collection date is unknown. That absence is itself
a metric (prov.undated_rate), and the default policy flags it.

When the files did come from somewhere, a sidecar JSON Lines file supplies what the directory
cannot: one object per document keyed by "locator" (the path relative to the corpus root),
carrying any of source_system, source_id, collected_at, custody, markings, parent_hash,
reliability and media_type, in the envelope's own shapes. The sidecar is strict: an unknown
field or a locator that is not in the corpus is an error, because a silently ignored entry is
provenance that was claimed and not recorded.
"""
from __future__ import annotations
import json
from pathlib import Path

from ..envelope import make_envelope
from ..manifest import BUNDLE_DIR

ADAPTER = ("plaintext", "0.1.0")
SIDECAR_FIELDS = ("source_system", "source_id", "collected_at", "custody", "markings", "parent_hash", "reliability", "media_type")
TEXT_SUFFIXES = {".txt": "text/plain", ".md": "text/markdown"}


class ProvenanceError(ValueError):
    pass


def load_provenance(path) -> dict[str, dict]:
    """locator -> sidecar fields. Validates shape; the envelope schema validates values at ingest."""
    out: dict[str, dict] = {}
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            raise ProvenanceError(f"{path}:{n}: not JSON ({e.msg})") from e
        if not isinstance(entry, dict) or "locator" not in entry:
            raise ProvenanceError(f"{path}:{n}: each entry is an object with a 'locator'")
        bad = sorted(k for k in entry if k != "locator" and k not in SIDECAR_FIELDS)
        if bad:
            raise ProvenanceError(f"{path}:{n}: unknown field(s) {', '.join(bad)}; allowed: {', '.join(SIDECAR_FIELDS)}")
        loc = entry["locator"]
        if loc in out:
            raise ProvenanceError(f"{path}:{n}: locator {loc!r} appears twice")
        out[loc] = {k: v for k, v in entry.items() if k != "locator"}
    return out


def docs_from_dir(corpus_dir, provenance=None):
    """Yield {'envelope', 'text'} for every file under corpus_dir, except the bundle itself."""
    corpus_dir = Path(corpus_dir)
    extra = load_provenance(provenance) if provenance else {}
    seen = set()
    for p in sorted(corpus_dir.rglob("*")):
        if not p.is_file() or BUNDLE_DIR in p.parts:
            continue
        locator = p.relative_to(corpus_dir).as_posix()
        seen.add(locator)
        data = p.read_bytes()
        fields = dict(extra.get(locator, {}))
        source_system = fields.pop("source_system", "fs")
        media_type = fields.pop("media_type", TEXT_SUFFIXES.get(p.suffix.lower()))
        env = make_envelope(data, source_system=source_system, source_locator=locator,
                            adapter_name=ADAPTER[0], adapter_version=ADAPTER[1], media_type=media_type, **fields)
        yield {"envelope": env, "text": data.decode("utf-8", errors="replace")}
    unknown = sorted(set(extra) - seen)
    if unknown:
        raise ProvenanceError(f"{provenance}: locator(s) not in the corpus: {', '.join(unknown)}")
