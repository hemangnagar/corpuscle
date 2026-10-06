"""Triage investigator, tool surface, proposals and approval.

Runs with a scripted model: the loop, the logging, the proposal store and the re-signing are
exercised exactly as a live run exercises them, without a network. The one thing not tested here
is the model's judgement.
"""
import json, shutil
from pathlib import Path
import pytest

from corpuscle import proposals
from corpuscle.cli import _docs_from_dir
from corpuscle.manifest import BUNDLE_DIR, build
from corpuscle.signing import Ed25519Signer
from corpuscle.tools import Investigation, TOOL_SPECS
from corpuscle.verify import verify
from corpuscle_agents.model import ScriptedModel, client_kwargs, text, tool_use
from corpuscle_agents.triage import AGENT, run_triage

FIXTURE = Path(__file__).parent / "fixtures" / "sample_corpus"


@pytest.fixture
def signer():
    return Ed25519Signer.generate("test")


@pytest.fixture
def scanned(tmp_path, signer):
    dst = tmp_path / "corpus"
    shutil.copytree(FIXTURE, dst)
    build(dst, corpus_id="sample", version_id="v1", docs=list(_docs_from_dir(dst)), signers=[signer])
    return dst


def _hashes(corpus):
    recs = [json.loads(l) for l in (corpus / BUNDLE_DIR / "records.jsonl").read_text().splitlines()]
    return {r["envelope"]["source_locator"]: r["doc_hash"] for r in recs}


def _manifest(corpus):
    return json.loads((corpus / BUNDLE_DIR / "manifest.json").read_text())


def _good_script(h):
    a, b = h["report-11.txt"], h["report-11-rev2.txt"]
    return [
        [text("Reading the finding."), tool_use("get_finding", {"finding_id": "DUP-002"})],
        [tool_use("diff_documents", {"doc_hash_a": a, "doc_hash_b": b}), tool_use("get_record", {"doc_hash": a})],
        [text("Two revisions of one report."),
         tool_use("propose", {"finding_id": "DUP-002", "assessment": "real",
                              "narrative": f"Documents {a[:12]} and {b[:12]} differ by one word; they are revisions of the same report kept side by side. For a retrieval corpus this is a real duplicate.",
                              "evidence": [a, b],
                              "remediation": {"action": "keep the newest revision of report-11", "predicted_effect": "dup.near_rate falls from 0.2857 to 0.1429"}})],
    ]


# tool surface

def test_tools_read_only_but_propose(scanned):
    inv = Investigation(scanned, scanned)
    h = _hashes(scanned)
    assert {f["finding_id"] for f in inv.list_findings()} >= {"DUP-001", "DUP-002", "PROV-001", "PROV-002", "INT-001"}
    assert inv.get_finding("DUP-002")["status"] == "fail"
    rec = inv.get_record(h["memo-01.txt"])
    assert "exact_duplicate" in rec["flags"] and "text" not in rec
    d = inv.diff_documents(h["report-11.txt"], h["report-11-rev2.txt"])
    assert d["similarity"] > 0.98 and d["changes"] == [{"op": "replace", "a": "to", "b": "for", "at_word": d["changes"][0]["at_word"]}]
    doc = inv.read_document(h["short-09.txt"])
    assert doc["chars"] == 2 and not doc["truncated"]


def test_every_call_is_logged_including_errors(scanned):
    inv = Investigation(scanned, scanned)
    r, err, entry = inv.call("get_finding", {"finding_id": "DUP-002"})
    assert not err and entry["tool"] == "get_finding" and len(entry["args_hash"]) == 64 and len(entry["result_hash"]) == 64
    r, err, entry = inv.call("get_finding", {"finding_id": "NOPE"})
    assert err and "no finding" in r["error"] and entry["result_hash"]
    r, err, entry = inv.call("drop_table", {})
    assert err and "no tool named" in r["error"]
    r, err, entry = inv.call("get_record", {"wrong": 1})
    assert err


def test_agent_cannot_set_measured_fields(scanned):
    inv = Investigation(scanned, scanned)
    h = _hashes(scanned)
    r, err, _ = inv.call("propose", {"finding_id": "DUP-002", "assessment": "artifact", "narrative": "n", "evidence": [h["report-11.txt"]],
                                     "observed": 0.0, "severity": "none"})
    assert err and "core measured those" in r["error"] and inv.proposals == []
    r, err, _ = inv.call("propose", {"finding_id": "DUP-002", "assessment": "artifact", "narrative": "n", "evidence": ["ab" * 32]})
    assert err and "no record" in r["error"]


def test_bundle_only_investigation_has_no_text(scanned):
    inv = Investigation(scanned, None)
    h = _hashes(scanned)
    r, err, _ = inv.call("read_document", {"doc_hash": h["memo-01.txt"]})
    assert err and "not available" in r["error"]


def test_tampered_document_is_refused(scanned):
    h = _hashes(scanned)
    (scanned / "report-11.txt").write_text("changed")
    inv = Investigation(scanned, scanned)
    r, err, _ = inv.call("read_document", {"doc_hash": h["report-11.txt"]})
    assert err and "no longer matches" in r["error"]


# the loop

def test_triage_produces_a_logged_proposal(scanned):
    h = _hashes(scanned)
    model = ScriptedModel(_good_script(h))
    pr = run_triage(scanned, "DUP-002", model)
    assert pr["status"] == "pending" and pr["kind"] == "finding" and pr["agent"] == AGENT and pr["model"] == "scripted"
    assert pr["payload"]["assessment"] == "real" and pr["payload"]["remediation"]["action"].startswith("keep")
    assert [e["doc_hash"] for e in pr["evidence"]] == [h["report-11.txt"], h["report-11-rev2.txt"]]
    run = pr["agent_run"]
    assert [c["tool"] for c in run["tool_calls"]] == ["get_finding", "diff_documents", "get_record", "propose"]
    assert all(len(c["args_hash"]) == 64 and len(c["result_hash"]) == 64 for c in run["tool_calls"])
    assert run["agent"] == AGENT and run["started_at"] <= run["finished_at"] and "revisions" in run["conclusion"]
    # the model saw the finding, the tool specs, and both tool results in one user message
    assert "DUP-002" in model.requests[0]["messages"][0]["content"]
    assert [t["name"] for t in model.requests[0]["tools"]] == [t["name"] for t in TOOL_SPECS]
    second_results = model.requests[2]["messages"][4]["content"]
    assert [r["type"] for r in second_results] == ["tool_result", "tool_result"] and not any(r["is_error"] for r in second_results)
    # and nothing in the bundle changed: a proposal is not an amendment
    assert _manifest(scanned)["agent_runs"] == [] and "assessment" not in _manifest(scanned)["findings"][1]


def test_tool_errors_go_back_to_the_model_and_into_the_log(scanned):
    h = _hashes(scanned)
    script = [[tool_use("get_record", {"doc_hash": "zz"})]] + _good_script(h)
    model = ScriptedModel(script)
    pr = run_triage(scanned, "DUP-002", model)
    assert model.requests[1]["messages"][2]["content"][0]["is_error"] is True
    assert pr["agent_run"]["tool_calls"][0]["tool"] == "get_record" and len(pr["agent_run"]["tool_calls"]) == 5
    assert pr["payload"]["assessment"] == "real"


def test_no_proposal_means_inconclusive_not_silence(scanned):
    model = ScriptedModel([[tool_use("get_finding", {"finding_id": "DUP-002"})], [text("I am not sure.")]])
    pr = run_triage(scanned, "DUP-002", model)
    assert pr["payload"]["assessment"] == "inconclusive" and "I am not sure." in pr["payload"]["narrative"]
    assert pr["evidence"] == [] and len(pr["agent_run"]["tool_calls"]) == 1


def test_refusal_is_recorded_as_inconclusive(scanned):
    model = ScriptedModel([[text("")]], stop_reasons=["refusal"])
    pr = run_triage(scanned, "DUP-002", model)
    assert pr["payload"]["assessment"] == "inconclusive" and "declined" in pr["agent_run"]["conclusion"]


def test_turn_limit_ends_the_run(scanned):
    model = ScriptedModel([[tool_use("list_findings", {})]] * 30)
    pr = run_triage(scanned, "DUP-002", model, max_turns=3)
    assert len(pr["agent_run"]["tool_calls"]) == 3 and pr["payload"]["assessment"] == "inconclusive"


# approval

def test_approval_amends_and_resigns(scanned, signer):
    h = _hashes(scanned)
    before = _manifest(scanned)
    pr = run_triage(scanned, "DUP-002", ScriptedModel(_good_script(h)))
    m = proposals.approve(scanned, pr["proposal_id"], "Dana Reyes, ISSM", [signer])
    f = next(x for x in m["findings"] if x["finding_id"] == "DUP-002")
    assert f["assessment"] == "real" and f["approved_by"] == "Dana Reyes, ISSM" and f["approved_at"]
    assert f["remediation"]["predicted_effect"].startswith("dup.near_rate")
    assert f["status"] == "fail" and f["severity"] == "high" and f["observed"] == before["findings"][1]["observed"]  # untouched
    assert f["evidence"] == before["findings"][1]["evidence"]  # the gate's evidence stays
    assert len(m["agent_runs"]) == 1 and m["agent_runs"][0]["proposal_ids"] == [pr["proposal_id"]]
    assert [c["tool"] for c in m["agent_runs"][0]["tool_calls"]][-1] == "propose"
    assert m["corpus"]["merkle_root"] == before["corpus"]["merkle_root"] and m["records_hash"] == before["records_hash"]
    assert m["results"] == before["results"]
    rep = verify(scanned, [signer.verifier()], corpus_dir=scanned)
    assert rep.ok and rep.manifest["agent_runs"] == m["agent_runs"]
    assert proposals.get(scanned, pr["proposal_id"])["status"] == "approved"


def test_approval_rules(scanned, signer):
    h = _hashes(scanned)
    pr = run_triage(scanned, "DUP-002", ScriptedModel(_good_script(h)))
    with pytest.raises(proposals.ProposalError, match="identity"):
        proposals.approve(scanned, pr["proposal_id"], "  ", [signer])
    with pytest.raises(proposals.ProposalError, match="no proposal"):
        proposals.approve(scanned, "prop-nope", "x", [signer])
    proposals.approve(scanned, pr["proposal_id"], "x", [signer])
    with pytest.raises(proposals.ProposalError, match="already approved"):
        proposals.approve(scanned, pr["proposal_id"], "x", [signer])
    pr2 = run_triage(scanned, "DUP-002", ScriptedModel(_good_script(h)))
    with pytest.raises(proposals.ProposalError, match="already carries"):
        proposals.approve(scanned, pr2["proposal_id"], "x", [signer])
    r = proposals.reject(scanned, pr2["proposal_id"], "x", "superseded")
    assert r["status"] == "rejected" and r["reason"] == "superseded"


def test_approval_needs_a_gated_finding(scanned, signer):
    p = proposals.submit(scanned, {"kind": "finding", "agent": "t", "model": "s", "evidence": [],
                                   "payload": {"finding_id": "GHOST-1", "assessment": "real", "narrative": "n"}},
                         {"agent": "t", "model": "s", "started_at": "2026-01-01T00:00:00Z", "tool_calls": []})
    with pytest.raises(proposals.ProposalError, match="not in the manifest"):
        proposals.approve(scanned, p["proposal_id"], "x", [signer])
    with pytest.raises(proposals.ProposalError, match="may not set"):
        proposals.submit(scanned, {"kind": "finding", "payload": {"finding_id": "DUP-002", "observed": 0}}, {})


def test_amended_manifest_still_detects_tampering(scanned, signer):
    h = _hashes(scanned)
    pr = run_triage(scanned, "DUP-002", ScriptedModel(_good_script(h)))
    proposals.approve(scanned, pr["proposal_id"], "x", [signer])
    (scanned / "memo-02.txt").write_text("edited")
    rep = verify(scanned, [signer.verifier()], corpus_dir=scanned)
    assert not rep.ok and rep.changed == ["memo-02.txt"]


# credentials

def test_project_key_goes_straight_to_the_api():
    assert client_kwargs({}) == {}
    assert client_kwargs({"ANTHROPIC_API_KEY": "x"}) == {}  # SDK resolves that one itself
    kw = client_kwargs({"CORPUSCLE_ANTHROPIC_KEY": "sk-test", "ANTHROPIC_BASE_URL": "https://harness.example"})
    assert kw == {"api_key": "sk-test", "base_url": "https://api.anthropic.com"}  # harness proxy ignored
    kw = client_kwargs({"CORPUSCLE_ANTHROPIC_KEY": "sk-test", "CORPUSCLE_ANTHROPIC_BASE_URL": "https://bedrock.example"})
    assert kw["base_url"] == "https://bedrock.example"


def test_anthropic_model_constructs_with_project_key(monkeypatch):
    pytest.importorskip("anthropic")
    from corpuscle_agents.model import AnthropicModel
    monkeypatch.setenv("CORPUSCLE_ANTHROPIC_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://harness.example")
    m = AnthropicModel()
    assert str(m.client.base_url).startswith("https://api.anthropic.com") and m.model_id == "claude-opus-5-5"
