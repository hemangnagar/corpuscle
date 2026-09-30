"""Triage investigator: the first agent.

Given one finding from a signed manifest, it investigates through the logged tool surface,
decides whether the defect is real, an artifact of the measurement, or inconclusive, and submits
a proposal. It cannot change a number, a threshold, a status or a severity; it cannot write to
the bundle; and its proposal executes only when a named approver accepts it. Every tool call,
including failed ones, is hashed into the agent run that approval signs into the manifest.

If the model ends without proposing, or is refused, an inconclusive proposal is submitted
anyway: an investigation that happened leaves a record, never silence.
"""
from __future__ import annotations
import json

from corpuscle import proposals
from corpuscle.envelope import now_iso
from corpuscle.tools import TOOL_SPECS, Investigation

from .model import Model

AGENT = "triage-investigator"
MAX_TURNS = 12

SYSTEM = """You are the triage investigator for a corpus datasheet.

A deterministic core has measured a corpus and a policy gate has raised a finding. Your job is to \
find out why, using the tools, and to say whether the defect is real (present and material for the \
corpus's intended use), an artifact (the measurement is correct but the cause is benign or \
expected), or inconclusive.

Rules you cannot break:
- You never compute or restate a measurement as your own. The observed value, threshold, status and \
severity come from the core and stay as they are; you may not set them.
- You conclude from evidence you actually examined. Cite documents by doc_hash. Do not quote \
personal data, credentials or marked text in your narrative; describe it.
- Look before you conclude: read the finding, then examine its evidence with get_record, \
diff_documents and read_document as needed. Two or three well-chosen calls usually suffice.
- Finish by calling propose exactly once. Keep the narrative to two to five sentences written for \
an authorizing official. If you recommend a remediation, say what it would do to the measured value.
- If the tools cannot show you enough, propose inconclusive and say what is missing.

Nothing you propose takes effect until a named approver accepts it."""


def run_triage(bundle_root, finding_id: str, model: Model, corpus_dir=None, max_turns: int = MAX_TURNS) -> dict:
    """Investigate one finding. Returns the stored proposal (with its agent_run)."""
    inv = Investigation(bundle_root, corpus_dir if corpus_dir is not None else bundle_root)
    finding = inv.get_finding(finding_id)
    started = now_iso()
    tool_calls: list[dict] = []
    conclusion = ""
    messages = [{"role": "user", "content":
                 f"Investigate finding {finding_id}.\n\n{json.dumps(finding, indent=1, sort_keys=True)}\n\n"
                 f"Corpus {inv.manifest['corpus']['corpus_id']} version {inv.manifest['corpus']['version_id']}, "
                 f"{inv.manifest['corpus']['document_count']} documents, policy {inv.manifest['run']['policy_version']}."}]

    for _ in range(max_turns):
        resp = model.create(system=SYSTEM, messages=messages, tools=TOOL_SPECS)
        messages.append({"role": "assistant", "content": resp.content})
        texts = [b.text for b in resp.content if b.type == "text"]
        if texts:
            conclusion = texts[-1]
        if resp.stop_reason == "refusal":
            conclusion = "model declined the investigation" + (f": {resp.stop_details.explanation}" if getattr(resp, "stop_details", None) else "")
            break
        uses = [b for b in resp.content if b.type == "tool_use"]
        if not uses:
            break
        results = []
        for u in uses:
            args = u.input if isinstance(u.input, dict) else json.loads(u.input)
            result, is_error, entry = inv.call(u.name, args)
            tool_calls.append(entry)
            results.append({"type": "tool_result", "tool_use_id": u.id, "is_error": is_error,
                            "content": json.dumps(result, ensure_ascii=False)})
        messages.append({"role": "user", "content": results})
        if inv.proposals:
            break
        if resp.stop_reason == "max_tokens":
            conclusion = "model output was cut off before a proposal"
            break

    if inv.proposals:
        proposal = inv.proposals[-1]
        conclusion = conclusion or proposal["payload"]["narrative"]
    else:
        proposal = {"kind": "finding", "evidence": [],
                    "payload": {"finding_id": finding_id, "assessment": "inconclusive",
                                "narrative": f"The investigator did not reach a conclusion: {conclusion or 'no proposal was made'}."}}
    run = {"agent": AGENT, "model": model.model_id, "started_at": started, "finished_at": now_iso(),
           "tool_calls": tool_calls, "conclusion": conclusion[:2000]}
    return proposals.submit(bundle_root, {**proposal, "agent": AGENT, "model": model.model_id}, run)
