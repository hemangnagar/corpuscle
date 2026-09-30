"""Finding gate and duplication family.

The demo the positioning promises: a scan that ends in a signed finding a model could not
have produced about its own corpus. The fixture carries one exact pair (memo-01/memo-04) and
two near pairs (report-11/-rev2, bulletin-12/-copy); short-09 has no shingles.
"""
import json, shutil
from pathlib import Path
import pytest

from corpuscle import gate
from corpuscle.analyzers.duplication import DuplicationAnalyzer, SCRATCH
from corpuscle.cli import _docs_from_dir
from corpuscle.manifest import BUNDLE_DIR, build
from corpuscle.signing import Ed25519Signer
from corpuscle.verify import verify

FIXTURE = Path(__file__).parent / "fixtures" / "sample_corpus"


@pytest.fixture
def corpus(tmp_path):
    dst = tmp_path / "corpus"
    shutil.copytree(FIXTURE, dst)
    return dst


@pytest.fixture
def signer():
    return Ed25519Signer.generate("test")


def _scan(corpus, signer, **kw):
    return build(corpus, corpus_id="sample", version_id="v1", docs=list(_docs_from_dir(corpus)), signers=[signer], **kw)


def _records(corpus):
    return [json.loads(l) for l in (corpus / BUNDLE_DIR / "records.jsonl").read_text().splitlines()]


def _by_locator(corpus):
    return {r["envelope"]["source_locator"]: r for r in _records(corpus)}


# duplication family

def test_exact_and_near_metrics(corpus, signer):
    m = _scan(corpus, signer)
    by_id = {r["metric_id"]: r for r in m["results"]}
    assert by_id["dup.exact_count"]["value"] == 2
    assert by_id["dup.exact_rate"]["value"] == pytest.approx(2 / 14, abs=1e-6)
    assert by_id["dup.near_count"]["value"] == 4
    assert by_id["dup.near_rate"]["value"] == pytest.approx(4 / 14, abs=1e-6)


def test_flags_name_the_documents(corpus, signer):
    _scan(corpus, signer)
    recs = _by_locator(corpus)
    assert recs["memo-01.txt"]["flags"] == ["exact_duplicate"]
    assert recs["memo-04.txt"]["flags"] == ["exact_duplicate"]
    for n in ("report-11.txt", "report-11-rev2.txt", "bulletin-12.txt", "bulletin-12-copy.txt"):
        assert recs[n]["flags"] == ["near_duplicate"], n
    for n in ("memo-02.txt", "report-06.txt", "short-09.txt"):
        assert "flags" not in recs[n], n


def test_scratch_never_reaches_the_bundle(corpus, signer):
    _scan(corpus, signer)
    for r in _records(corpus):
        assert not any(k.startswith("_") for k in r["metrics"])


def test_near_duplicate_just_above_threshold_is_caught():
    """A pair at Jaccard ~0.87 that LSH banding at 0.8 would miss; the recall-weighted index catches it."""
    a = (FIXTURE / "bulletin-12.txt").read_text()
    b = (FIXTURE / "bulletin-12-copy.txt").read_text()
    docs = [{"envelope": {"doc_hash": "a" * 64}, "text": a}, {"envelope": {"doc_hash": "b" * 64}, "text": b},
            {"envelope": {"doc_hash": "c" * 64}, "text": (FIXTURE / "report-11.txt").read_text()}]
    an = DuplicationAnalyzer()
    recs = [{"doc_hash": d["envelope"]["doc_hash"], "metrics": an.per_document(d)} for d in docs]
    res = {r.metric_id: r.value for r in an.corpus(recs)}
    assert res["dup.near_count"] == 2
    assert [r.get("flags") for r in recs] == [["near_duplicate"], ["near_duplicate"], None]


def test_short_document_has_no_signature():
    an = DuplicationAnalyzer()
    assert an.per_document({"text": "four words only here"}) == {}
    assert SCRATCH in an.per_document({"text": "five words are enough here"})


def test_duplication_pins_recorded(corpus, signer):
    m = _scan(corpus, signer)
    pins = m["run"]["pins"]
    assert pins["analyzer:duplication"] == "0.1.0"
    assert pins["datasketch"]
    assert "threshold=0.8" in pins["minhash"] and "lsh_index=0.6" in pins["minhash"]


# finding gate

def test_default_policy_produces_signed_findings(corpus, signer):
    m = _scan(corpus, signer)
    f = {x["finding_id"]: x for x in m["findings"]}
    assert f["DUP-001"]["status"] == "fail" and f["DUP-001"]["severity"] == "medium"
    assert f["DUP-002"]["status"] == "fail" and f["DUP-002"]["severity"] == "high"
    assert f["DUP-002"]["framework"] == "corpuscle-default" and f["DUP-002"]["clause"] == "duplication.near"
    assert f["DUP-002"]["observed"] == pytest.approx(4 / 14, abs=1e-6)
    assert f["DUP-002"]["threshold"]["fail"] == {"op": ">", "value": 0.10}
    assert f["DUP-002"]["gate"]["verdict"] == "fail"
    # the findings are inside the signed statement, and the bundle still verifies
    rep = verify(corpus, [signer.verifier()], corpus_dir=corpus)
    assert rep.ok and rep.manifest["findings"] == m["findings"]


def test_evidence_is_the_flagged_documents(corpus, signer):
    m = _scan(corpus, signer)
    recs = _by_locator(corpus)
    near = {x["finding_id"]: x for x in m["findings"]}["DUP-002"]
    expected = {recs[n]["doc_hash"] for n in ("report-11.txt", "report-11-rev2.txt", "bulletin-12.txt", "bulletin-12-copy.txt")}
    assert {e["doc_hash"] for e in near["evidence"]} == expected
    exact = {x["finding_id"]: x for x in m["findings"]}["DUP-001"]
    assert [e["doc_hash"] for e in exact["evidence"]] == [recs["memo-01.txt"]["doc_hash"]]  # one hash, deduped


def test_policy_identity_travels_in_the_manifest(corpus, signer):
    m = _scan(corpus, signer)
    assert m["run"]["policy_version"] == "corpuscle-default/0.1.0"
    assert m["run"]["pins"]["policy:corpuscle-default"] == gate.load_policy()["_hash"]
    assert len(m["run"]["pins"]["policy:corpuscle-default"]) == 64


def test_findings_are_deterministic(corpus, signer):
    m1 = _scan(corpus, signer)
    m2 = _scan(corpus, signer)
    assert m1["findings"] == m2["findings"]
    assert m1["results"] == m2["results"]


def test_clean_subset_passes(corpus, signer, tmp_path):
    clean = tmp_path / "clean"
    clean.mkdir()
    for n in ("memo-01.txt", "memo-02.txt", "report-06.txt", "report-07.txt", "report-11.txt"):
        shutil.copy(corpus / n, clean / n)
    m = build(clean, corpus_id="sample", version_id="clean", docs=list(_docs_from_dir(clean)), signers=[signer])
    assert [(f["status"], f["severity"]) for f in m["findings"]] == [("pass", "none"), ("pass", "none")]
    assert all("evidence" not in f for f in m["findings"])


def test_no_policy_means_no_findings(corpus, signer):
    m = _scan(corpus, signer, policy=None)
    assert m["findings"] == [] and m["run"]["policy_version"] == "none"
    assert not any(k.startswith("policy:") for k in m["run"]["pins"])


def test_flag_band_and_inconclusive(corpus, signer):
    policy = {
        "policy_id": "t", "policy_version": "1", "framework": "test",
        "rules": [
            {"rule_id": "T-1", "clause": "a", "title": "near", "metric_id": "dup.near_rate",
             "flag": {"op": ">", "value": 0.05}, "fail": {"op": ">", "value": 0.5},
             "severity": {"flag": "low", "fail": "critical"}},
            {"rule_id": "T-2", "clause": "b", "title": "missing", "metric_id": "pii.hit_rate",
             "fail": {"op": ">", "value": 0}, "severity": {"fail": "high"}},
        ],
    }
    m = _scan(corpus, signer, policy=policy)
    f = {x["finding_id"]: x for x in m["findings"]}
    assert f["T-1"]["status"] == "flag" and f["T-1"]["severity"] == "low"
    assert f["T-2"]["status"] == "inconclusive" and f["T-2"]["severity"] == "none"
    assert "not reported" in f["T-2"]["gate"]["reason"]
    assert m["run"]["policy_version"] == "t/1"
    assert m["run"]["pins"]["policy:t"] == gate.policy_hash(policy)


def test_invalid_policy_rejected_with_a_readable_message(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("policy_id: x\npolicy_version: '1'\nframework: f\nrules:\n  - rule_id: R\n    clause: c\n    title: t\n    metric_id: m\n    severity: {fail: 'urgent'}\n")
    with pytest.raises(gate.PolicyError, match=r"rules/0/severity/fail"):
        gate.load_policy(bad)


def test_numeric_version_is_accepted_as_string(tmp_path):
    """YAML reads 2026.09 as a float; a version is a label, so it is taken as written."""
    p = tmp_path / "p.yaml"
    p.write_text("policy_id: acme\npolicy_version: 2026.09\nframework: acme\nrules: []\n")
    pol = gate.load_policy(p)
    assert pol["policy_version"] == "2026.09" and gate.policy_version(pol) == "acme/2026.09"


def test_agent_findings_append_after_gate(corpus, signer):
    extra = {"finding_id": "AGENT-1", "framework": "corpuscle-default", "clause": "duplication.near",
             "metric_ids": ["dup.near_rate"], "status": "flag", "severity": "low", "assessment": "artifact",
             "narrative": "Two revisions of one report; expected in a working folder."}
    m = _scan(corpus, signer, findings=[extra])
    assert [f["finding_id"] for f in m["findings"]] == ["DUP-001", "DUP-002", "AGENT-1"]
