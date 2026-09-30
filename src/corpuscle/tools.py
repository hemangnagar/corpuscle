"""The tool surface an agent investigates through. Deterministic, logged, read-only but for propose.

An agent never touches the bundle. It sees findings, records and documents through these calls,
each of which is logged as (tool, args_hash, result_hash) into the agent run that the approver
signs into the manifest. The only write is propose(), and a proposal changes nothing until a
named approver accepts it; even then it can carry an assessment, a narrative and a remediation,
never an observed value, a threshold, a status or a severity.

Reading a document is investigation, not measurement: the text is shown to the agent, hashed
into the log, and stored nowhere. MCP mirrors these calls one to one.
"""
from __future__ import annotations
import difflib
import json
import re
from pathlib import Path

from .hashing import sha256_bytes
from .manifest import BUNDLE_DIR

MAX_DOCUMENT_CHARS = 4000
MAX_DIFF_OPS = 20
_WORD = re.compile(r"\S+")

FORBIDDEN_PROPOSAL_KEYS = ("observed", "threshold", "status", "severity", "metric_ids", "gate", "framework", "clause")


def canonical_hash(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


class ToolError(ValueError):
    pass


TOOL_SPECS = [
    {"name": "list_findings", "description": "All findings in the signed manifest: id, clause, status, severity, observed value.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_finding", "description": "One finding in full, including its evidence doc_hashes and the gate's reason.",
     "input_schema": {"type": "object", "required": ["finding_id"], "additionalProperties": False,
                      "properties": {"finding_id": {"type": "string"}}}},
    {"name": "get_record", "description": "The per-document record for a doc_hash: provenance envelope, per-document metrics, flags. Never document text.",
     "input_schema": {"type": "object", "required": ["doc_hash"], "additionalProperties": False,
                      "properties": {"doc_hash": {"type": "string"}}}},
    {"name": "read_document", "description": f"The text of a document by doc_hash, up to {MAX_DOCUMENT_CHARS} characters. Only when the corpus files are present.",
     "input_schema": {"type": "object", "required": ["doc_hash"], "additionalProperties": False,
                      "properties": {"doc_hash": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 100, "maximum": MAX_DOCUMENT_CHARS}}}},
    {"name": "diff_documents", "description": "Word-level comparison of two documents: similarity ratio, word counts, and the changed spans.",
     "input_schema": {"type": "object", "required": ["doc_hash_a", "doc_hash_b"], "additionalProperties": False,
                      "properties": {"doc_hash_a": {"type": "string"}, "doc_hash_b": {"type": "string"}}}},
    {"name": "propose", "strict": True,
     "description": "Submit your conclusion on one finding. Call it exactly once, last. It changes nothing until a named approver accepts it. "
                    "You may not supply observed, threshold, status or severity: the core measured those.",
     "input_schema": {"type": "object", "required": ["finding_id", "assessment", "narrative", "evidence", "remediation"], "additionalProperties": False,
                      "properties": {
                          "finding_id": {"type": "string"},
                          "assessment": {"type": "string", "enum": ["real", "artifact", "inconclusive"],
                                         "description": "real: the defect is present and matters for the corpus's use. artifact: the measurement is correct but the cause is benign or expected. inconclusive: you could not tell from the evidence."},
                          "narrative": {"type": "string", "description": "Two to five sentences for the authorizing official. Cite doc_hashes, never quote personal data."},
                          "evidence": {"type": "array", "items": {"type": "string"}, "description": "doc_hashes you examined that support the conclusion."},
                          "remediation": {"anyOf": [{"type": "null"}, {"type": "object", "required": ["action", "predicted_effect"], "additionalProperties": False,
                                                     "properties": {"action": {"type": "string"}, "predicted_effect": {"type": "string"}}}]}}}},
]


class Investigation:
    """A bundle opened for investigation. corpus_dir may be None (bundle only: no read_document, no diff)."""

    def __init__(self, bundle_root, corpus_dir=None):
        b = Path(bundle_root) / BUNDLE_DIR
        self.bundle_root = Path(bundle_root)
        self.corpus_dir = Path(corpus_dir) if corpus_dir is not None else None
        self.manifest = json.loads((b / "manifest.json").read_text())
        self.records = {}
        for line in (b / "records.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                self.records.setdefault(r["doc_hash"], r)  # exact duplicates share a hash; first locator wins
        self.proposals: list[dict] = []

    # tools

    def list_findings(self) -> list[dict]:
        return [{k: f.get(k) for k in ("finding_id", "clause", "status", "severity", "observed")} for f in self.manifest["findings"]]

    def get_finding(self, finding_id: str) -> dict:
        for f in self.manifest["findings"]:
            if f["finding_id"] == finding_id:
                return f
        raise ToolError(f"no finding {finding_id}")

    def get_record(self, doc_hash: str) -> dict:
        if doc_hash not in self.records:
            raise ToolError(f"no record for {doc_hash}")
        return self.records[doc_hash]

    def _text(self, doc_hash: str) -> str:
        if self.corpus_dir is None:
            raise ToolError("corpus files are not available to this investigation")
        rec = self.get_record(doc_hash)
        p = self.corpus_dir / rec["envelope"]["source_locator"]
        if not p.exists():
            raise ToolError(f"{rec['envelope']['source_locator']} is not present")
        data = p.read_bytes()
        if sha256_bytes(data) != doc_hash:
            raise ToolError(f"{rec['envelope']['source_locator']} no longer matches its record")
        return data.decode("utf-8", errors="replace")

    def read_document(self, doc_hash: str, max_chars: int = MAX_DOCUMENT_CHARS) -> dict:
        t = self._text(doc_hash)
        n = min(int(max_chars), MAX_DOCUMENT_CHARS)
        return {"doc_hash": doc_hash, "chars": len(t), "truncated": len(t) > n, "text": t[:n]}

    def diff_documents(self, doc_hash_a: str, doc_hash_b: str) -> dict:
        a, b = _WORD.findall(self._text(doc_hash_a)), _WORD.findall(self._text(doc_hash_b))
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        ops = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            ops.append({"op": tag, "a": " ".join(a[i1:i2]), "b": " ".join(b[j1:j2]), "at_word": i1})
            if len(ops) >= MAX_DIFF_OPS:
                break
        return {"similarity": round(sm.ratio(), 4), "words_a": len(a), "words_b": len(b),
                "changes": ops, "changes_truncated": len(ops) >= MAX_DIFF_OPS}

    def propose(self, finding_id: str, assessment: str, narrative: str, evidence: list[str], remediation: dict | None = None, **extra) -> dict:
        bad = [k for k in extra if k in FORBIDDEN_PROPOSAL_KEYS]
        if bad:
            raise ToolError(f"a proposal may not set {', '.join(bad)}: the core measured those")
        if extra:
            raise ToolError(f"unknown proposal fields: {', '.join(sorted(extra))}")
        self.get_finding(finding_id)
        for h in evidence:
            self.get_record(h)
        p = {"kind": "finding", "payload": {"finding_id": finding_id, "assessment": assessment, "narrative": narrative}}
        if remediation:
            p["payload"]["remediation"] = remediation
        p["evidence"] = [{"doc_hash": h} for h in dict.fromkeys(evidence)]
        self.proposals.append(p)
        return {"accepted": True, "finding_id": finding_id, "assessment": assessment}

    # dispatch

    def call(self, name: str, args: dict) -> tuple[dict, bool, dict]:
        """Run one tool. Returns (result, is_error, log_entry). Every call is logged, errors included."""
        entry = {"tool": name, "args_hash": canonical_hash(args)}
        fn = getattr(self, name, None) if name in {t["name"] for t in TOOL_SPECS} else None
        try:
            if fn is None:
                raise ToolError(f"no tool named {name}")
            result, err = fn(**args), False
        except (ToolError, TypeError) as e:
            result, err = {"error": str(e)}, True
        entry["result_hash"] = canonical_hash(result)
        return result, err, entry
