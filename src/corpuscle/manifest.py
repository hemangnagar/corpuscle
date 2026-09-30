"""Build the bundle:  <out>/.corpuscle/{records.jsonl, manifest.json, manifest.dsse.json}

records.jsonl  one per-document record per line, sorted by doc_hash
manifest.json  corpus-level statement (unsigned copy, for humans and guards)
manifest.dsse.json  the signed envelope; what verify() checks
"""
from __future__ import annotations
import json, uuid
from pathlib import Path
from typing import Iterable

from . import __version__
from .analyzers import REGISTRY, Result
from .analyzers import duplication, volume  # noqa: F401  registers analyzers
from .catalog import version as catalog_version
from .envelope import now_iso, validate
from . import gate
from .hashing import HASH_ALG, merkle_root, sha256_bytes
from .signing import Signer, sign_manifest

BUNDLE_DIR = ".corpuscle"


def run_analyzers(docs: Iterable[dict], analyzers: list[str] | None = None) -> tuple[list[dict], list[Result], dict]:
    """docs: dicts with 'envelope' (validated) and optional 'text'. Returns (records, results, pins)."""
    names = analyzers or list(REGISTRY)
    active = [REGISTRY[n] for n in names]
    records = []
    for d in docs:
        rec = {"doc_hash": d["envelope"]["doc_hash"], "envelope": d["envelope"], "metrics": {}}
        for a in active:
            rec["metrics"].update(a.per_document({**d, **rec}))
        records.append(rec)
    records.sort(key=lambda r: r["doc_hash"])
    results, pins = [], {}
    for a in active:
        results.extend(a.corpus(records))
        pins.update(a.pins)
        pins[f"analyzer:{a.name}"] = a.version
    for r in records:
        r["metrics"] = {k: v for k, v in r["metrics"].items() if not k.startswith("_")}
        validate(r, "record.schema.json")
    return records, results, pins


def build(out_dir, *, corpus_id: str, version_id: str, docs: list[dict], signers: list[Signer],
          analyzers: list[str] | None = None, policy: dict | str | Path | None = gate.DEFAULT_POLICY,
          engine: str = "local", findings: list[dict] | None = None, agent_runs: list[dict] | None = None,
          derived_from: dict | None = None, markings: list[str] | None = None) -> dict:
    """policy: a loaded policy dict, a path to one, or None to skip the gate. Findings passed in
    (from an approved agent proposal, say) are appended after the gate's own."""
    started = now_iso()
    records, results, pins = run_analyzers(docs, analyzers)
    result_json = [r.to_json() for r in results]
    policy_version, gated = "none", []
    if policy is not None:
        if not isinstance(policy, dict):
            policy = gate.load_policy(policy)
        policy_version = gate.policy_version(policy)
        pins[f"policy:{policy['policy_id']}"] = gate.policy_hash(policy)
        gated = gate.evaluate(policy, result_json, records)
    bundle = Path(out_dir) / BUNDLE_DIR
    bundle.mkdir(parents=True, exist_ok=True)

    records_bytes = "".join(json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
                            for r in records).encode()
    (bundle / "records.jsonl").write_bytes(records_bytes)

    hashes = [r["doc_hash"] for r in records]
    corpus = {
        "corpus_id": corpus_id, "version_id": version_id,
        "merkle_root": merkle_root(hashes), "hash_alg": HASH_ALG,
        "document_count": len(records),
        "total_bytes": sum(r["envelope"]["size_bytes"] for r in records),
    }
    if derived_from:
        corpus["derived_from"] = derived_from
    if markings:
        corpus["markings"] = markings
    manifest = {
        "manifest_version": "0",
        "corpus": corpus,
        "run": {"run_id": str(uuid.uuid4()), "started_at": started, "finished_at": now_iso(),
                "engine": f"corpuscle/{__version__} {engine}", "catalog_version": catalog_version(),
                "policy_version": policy_version, "pins": pins},
        "records_hash": sha256_bytes(records_bytes),
        "records_count": len(records),
        "results": result_json,
        "findings": gated + (findings or []),
        "agent_runs": agent_runs or [],
    }
    validate(manifest, "manifest.schema.json")
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    (bundle / "manifest.dsse.json").write_text(json.dumps(sign_manifest(manifest, signers), indent=1))
    return manifest


def manifest_hash(bundle_dir) -> str:
    return sha256_bytes((Path(bundle_dir) / BUNDLE_DIR / "manifest.json").read_bytes())
