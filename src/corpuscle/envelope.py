"""Provenance envelope: captured at ingest, validated against the schema."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import jsonschema

from .hashing import HASH_ALG, sha256_bytes

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


@lru_cache
def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


@lru_cache
def _registry():
    from referencing import Registry, Resource
    reg = Registry()
    for p in SCHEMA_DIR.glob("*.schema.json"):
        s = json.loads(p.read_text())
        reg = reg.with_resource(s["$id"], Resource.from_contents(s))
    return reg


def validate(obj: dict, schema_name: str) -> None:
    jsonschema.Draft202012Validator(_schema(schema_name), registry=_registry()).validate(obj)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_envelope(data: bytes, *, source_system: str, source_locator: str, adapter_name: str,
                  adapter_version: str, media_type: str | None = None, **extra) -> dict:
    env = {
        "doc_hash": sha256_bytes(data),
        "hash_alg": HASH_ALG,
        "size_bytes": len(data),
        "source_system": source_system,
        "source_locator": source_locator,
        "ingested_at": now_iso(),
        "adapter": {"name": adapter_name, "version": adapter_version},
    }
    if media_type:
        env["media_type"] = media_type
    env.update({k: v for k, v in extra.items() if v is not None})
    validate(env, "provenance-envelope.schema.json")
    return env
