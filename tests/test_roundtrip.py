"""Fourteen-document round trip: hash, build, sign, verify, tamper, derive.

This is the smallest test that proves the architecture: the bundle is the only
artifact, it is verifiable offline, and every change to the corpus is detected.
"""
import json, shutil
from pathlib import Path
import pytest

from corpuscle.cli import _docs_from_dir
from corpuscle.hashing import merkle_proof, merkle_root, sha256_bytes
from corpuscle.manifest import BUNDLE_DIR, build
from corpuscle.signing import Ed25519Signer, open_envelope
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


def test_build_and_verify(corpus, signer):
    m = _scan(corpus, signer)
    assert m["corpus"]["document_count"] == 14
    assert (corpus / BUNDLE_DIR / "manifest.dsse.json").exists()
    rep = verify(corpus, [signer.verifier()], corpus_dir=corpus)
    assert rep.ok, str(rep)


def test_deterministic_root(corpus, signer):
    """Same corpus, same root and same records. Only ingested_at, which is provenance, may differ."""
    m1 = _scan(corpus, signer)
    r1 = (corpus / BUNDLE_DIR / "records.jsonl").read_text()
    m2 = _scan(corpus, signer)
    r2 = (corpus / BUNDLE_DIR / "records.jsonl").read_text()
    assert m1["corpus"]["merkle_root"] == m2["corpus"]["merkle_root"]
    strip = lambda text: [{**json.loads(l), "envelope": {k: v for k, v in json.loads(l)["envelope"].items() if k != "ingested_at"}}
                          for l in text.splitlines()]
    assert strip(r1) == strip(r2)
    assert m1["results"] == m2["results"] and m1["findings"] == m2["findings"]


def test_exact_duplicates_share_hash(corpus, signer):
    m = _scan(corpus, signer)
    recs = [json.loads(l) for l in (corpus / BUNDLE_DIR / "records.jsonl").read_text().splitlines()]
    hashes = [r["doc_hash"] for r in recs]
    assert len(hashes) == 14 and len(set(hashes)) == 13  # memo-01 and memo-04 are byte-identical


def test_tamper_document_detected(corpus, signer):
    _scan(corpus, signer)
    (corpus / "report-06.txt").write_text("edited after signing")
    rep = verify(corpus, [signer.verifier()], corpus_dir=corpus)
    assert not rep.ok and rep.changed == ["report-06.txt"]


def test_added_and_removed_detected(corpus, signer):
    _scan(corpus, signer)
    (corpus / "memo-02.txt").unlink()
    (corpus / "new-11.txt").write_text("late arrival")
    rep = verify(corpus, [signer.verifier()], corpus_dir=corpus)
    assert not rep.ok and rep.added == ["new-11.txt"] and len(rep.removed) == 1


def test_tamper_manifest_detected(corpus, signer):
    _scan(corpus, signer)
    p = corpus / BUNDLE_DIR / "manifest.dsse.json"
    env = json.loads(p.read_text())
    env["payload"] = env["payload"][:-4] + "AAAA"
    p.write_text(json.dumps(env))
    rep = verify(corpus, [signer.verifier()])
    assert not rep.ok and rep.checks["signature"] is False


def test_wrong_key_rejected(corpus, signer):
    _scan(corpus, signer)
    other = Ed25519Signer.generate("test")  # same keyid, different key
    rep = verify(corpus, [other.verifier()])
    assert not rep.ok


def test_records_tamper_detected(corpus, signer):
    _scan(corpus, signer)
    p = corpus / BUNDLE_DIR / "records.jsonl"
    p.write_text(p.read_text().replace('"fs"', '"s3"'))
    rep = verify(corpus, [signer.verifier()])
    assert not rep.ok and rep.checks["records hash"] is False


def test_merkle_proof_for_single_document(corpus, signer):
    m = _scan(corpus, signer)
    recs = [json.loads(l) for l in (corpus / BUNDLE_DIR / "records.jsonl").read_text().splitlines()]
    hashes = [r["doc_hash"] for r in recs]
    leaf = hashes[3]
    proof = merkle_proof(hashes, leaf)
    assert proof.verify(m["corpus"]["merkle_root"])
    assert not proof.verify(sha256_bytes(b"other root"))


def test_derived_subset_links_to_parent(corpus, signer, tmp_path):
    parent = _scan(corpus, signer)
    child_dir = tmp_path / "subset"
    child_dir.mkdir()
    for n in ("memo-01.txt", "report-06.txt", "report-07.txt"):
        shutil.copy(corpus / n, child_dir / n)
    child = build(child_dir, corpus_id="sample", version_id="v1-subset", docs=list(_docs_from_dir(child_dir)),
                  signers=[signer], derived_from={"parent_merkle_root": parent["corpus"]["merkle_root"],
                                                  "relation": "subset", "description": "three reports"})
    assert child["corpus"]["derived_from"]["parent_merkle_root"] == parent["corpus"]["merkle_root"]
    assert child["corpus"]["document_count"] == 3
    assert verify(child_dir, [signer.verifier()], corpus_dir=child_dir).ok


def test_statement_subject_is_merkle_root(corpus, signer):
    m = _scan(corpus, signer)
    env = json.loads((corpus / BUNDLE_DIR / "manifest.dsse.json").read_text())
    st = open_envelope(env, [signer.verifier()])
    assert st["subject"][0]["digest"]["sha256"] == m["corpus"]["merkle_root"]
    assert st["predicateType"].endswith("/manifest/v0")


def test_volume_results_present(corpus, signer):
    m = _scan(corpus, signer)
    by_id = {r["metric_id"]: r for r in m["results"]}
    assert by_id["vol.total_docs"]["value"] == 14
    assert by_id["vol.total_tokens"]["value"] > 0
    assert "p95" in by_id["cnt.token_count"]["distribution"]
    assert "analyzer:volume" in m["run"]["pins"]


FIXTURE_ROOT = "d0ad149212ec3606fe32125938d16cbba3080416dae2e2088ed35d5e9f598f78"


def test_fixture_root_is_platform_independent(corpus, signer):
    """The fixture corpus has one identity everywhere. A Windows checkout with autocrlf once produced a
    different root because the two multi-line fixtures gained CRLF endings; .gitattributes now pins
    the bytes, and this test fails loudly if a checkout ever changes them again."""
    assert _scan(corpus, signer)["corpus"]["merkle_root"] == FIXTURE_ROOT
