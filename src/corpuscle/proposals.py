"""Proposal store and approval. Nothing an agent proposes executes until a named approver accepts it.

Proposals live beside the bundle in .corpuscle/proposals/, one JSON file each, outside the signed
statement. Approval amends the manifest: the finding gains the agent's assessment, narrative and
remediation plus the approver's identity and time, the agent's run (every tool call, hashed) is
appended to agent_runs, and the statement is re-signed. Records, results, the Merkle root and the
gate's own verdicts are untouched: an approval adds to the record, it never rewrites a number.
"""
from __future__ import annotations
import json
from pathlib import Path

from .envelope import now_iso
from .manifest import BUNDLE_DIR, amend
from .signing import Signer
from .tools import FORBIDDEN_PROPOSAL_KEYS, canonical_hash

PROPOSALS_DIR = "proposals"
AMENDABLE = ("assessment", "narrative", "remediation")


class ProposalError(ValueError):
    pass


def _dir(bundle_root) -> Path:
    d = Path(bundle_root) / BUNDLE_DIR / PROPOSALS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def submit(bundle_root, proposal: dict, agent_run: dict) -> dict:
    """Store a proposal with the agent run that produced it. Returns the stored proposal."""
    bad = [k for k in proposal.get("payload", {}) if k in FORBIDDEN_PROPOSAL_KEYS]
    if bad:
        raise ProposalError(f"a proposal may not set {', '.join(bad)}")
    stored = {**proposal, "agent_run": agent_run, "submitted_at": now_iso(), "status": "pending"}
    stored["proposal_id"] = "prop-" + canonical_hash(stored)[:12]
    (_dir(bundle_root) / f"{stored['proposal_id']}.json").write_text(json.dumps(stored, indent=1, sort_keys=True))
    return stored


def list_proposals(bundle_root) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(_dir(bundle_root).glob("prop-*.json"))]


def get(bundle_root, proposal_id: str) -> dict:
    p = _dir(bundle_root) / f"{proposal_id}.json"
    if not p.exists():
        raise ProposalError(f"no proposal {proposal_id}")
    return json.loads(p.read_text())


def _save(bundle_root, proposal: dict) -> None:
    (_dir(bundle_root) / f"{proposal['proposal_id']}.json").write_text(json.dumps(proposal, indent=1, sort_keys=True))


def reject(bundle_root, proposal_id: str, approver: str, reason: str = "") -> dict:
    p = get(bundle_root, proposal_id)
    if p["status"] != "pending":
        raise ProposalError(f"{proposal_id} is already {p['status']}")
    p.update(status="rejected", decided_by=approver, decided_at=now_iso(), reason=reason)
    _save(bundle_root, p)
    return p


def approve(bundle_root, proposal_id: str, approver: str, signers: list[Signer]) -> dict:
    """Approve with a named identity. The gate must already have judged the finding. Re-signs the manifest."""
    if not approver or not approver.strip():
        raise ProposalError("an approver identity is required")
    p = get(bundle_root, proposal_id)
    if p["status"] != "pending":
        raise ProposalError(f"{proposal_id} is already {p['status']}")
    if p.get("kind") != "finding":
        raise ProposalError(f"cannot approve a proposal of kind {p.get('kind')!r} yet")
    manifest = json.loads((Path(bundle_root) / BUNDLE_DIR / "manifest.json").read_text())
    fid = p["payload"]["finding_id"]
    finding = next((f for f in manifest["findings"] if f["finding_id"] == fid), None)
    if finding is None:
        raise ProposalError(f"finding {fid} is not in the manifest")
    if not finding.get("gate", {}).get("verdict"):
        raise ProposalError(f"finding {fid} was not judged by the gate; nothing to approve against")
    if finding.get("approved_by"):
        raise ProposalError(f"finding {fid} already carries an approved assessment")
    when = now_iso()
    patch = {k: p["payload"][k] for k in AMENDABLE if k in p["payload"]}
    patch.update(approved_by=approver, approved_at=when)
    run = {**p["agent_run"], "proposal_ids": [proposal_id]}
    manifest = amend(bundle_root, findings_patch={fid: patch}, agent_runs=[run], signers=signers)
    p.update(status="approved", decided_by=approver, decided_at=when)
    _save(bundle_root, p)
    return manifest
