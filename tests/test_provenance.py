"""Provenance family and the filesystem adapter's sidecar.

Everything here is computed from the envelope. The fixture's sidecar gives the fourteen files
sources, dates, custody and ids, with two deliberate defects: two files are undated, and the
two report-11 revisions share a source id over different bytes.
"""
import json, shutil
from pathlib import Path
import pytest

from corpuscle.adapters.fs import ProvenanceError, docs_from_dir, load_provenance
from corpuscle.analyzers.provenance import ProvenanceAnalyzer
from corpuscle.envelope import make_envelope
from corpuscle.manifest import BUNDLE_DIR, build
from corpuscle.signing import Ed25519Signer

FIXTURE = Path(__file__).parent / "fixtures" / "sample_corpus"
SIDECAR = Path(__file__).parent / "fixtures" / "sample_corpus.provenance.jsonl"


@pytest.fixture
def corpus(tmp_path):
    dst = tmp_path / "corpus"
    shutil.copytree(FIXTURE, dst)
    return dst


@pytest.fixture
def signer():
    return Ed25519Signer.generate("test")


def _scan(corpus, signer, provenance=SIDECAR):
    return build(corpus, corpus_id="sample", version_id="v1", docs=list(docs_from_dir(corpus, provenance)), signers=[signer])


def _results(m):
    return {r["metric_id"]: r["value"] for r in m["results"]}


def _records(corpus):
    return {r["envelope"]["source_locator"]: r for r in map(json.loads, (corpus / BUNDLE_DIR / "records.jsonl").read_text().splitlines())}


# analyzer on synthetic envelopes

def _doc(i, **fields):
    data = f"document {i}".encode()
    return {"doc_hash": make_envelope(data, source_system=fields.pop("source_system", "s"), source_locator=f"d{i}",
                                      adapter_name="t", adapter_version="0", **fields)["doc_hash"], "metrics": {}}


def _rec(i, **fields):
    r = _doc(i, **fields)
    r["envelope"] = make_envelope(f"document {i}".encode(), source_system=fields.pop("source_system", "s"),
                                  source_locator=f"d{i}", adapter_name="t", adapter_version="0", **fields)
    return r


def test_metrics_from_envelopes():
    recs = [
        _rec(1, collected_at="2026-01-05T00:00:00Z", source_id="A", custody=[{"actor": "x", "at": "2026-01-05T00:00:00Z"}],
             reliability={"source": "A", "information": "1"}),
        _rec(2, collected_at="2026-01-01T00:00:00Z", source_id="A"),                     # same id, different bytes
        _rec(3, source_system="other", source_id="A"),                                    # same id, other system: fine
        _rec(4, parent_hash="ab" * 32),
    ]
    res = {r.metric_id: r.value for r in ProvenanceAnalyzer().corpus(recs)}
    assert res["prov.source_histogram"] == {"other": {"docs": 1, "bytes": 10}, "s": {"docs": 3, "bytes": 30}}
    assert res["prov.date_range"] == {"min": "2026-01-01T00:00:00Z", "max": "2026-01-05T00:00:00Z", "dated": 2}
    assert res["prov.undated_rate"] == 0.5
    assert res["prov.custody_complete_rate"] == 0.25
    assert res["prov.reliability_histogram"] == {"A1": 1, "unrated": 3}
    assert res["prov.derived_share"] == 0.25
    assert res["prov.duplicate_id_count"] == 2 and res["prov.duplicate_id_rate"] == pytest.approx(2 / 3, abs=1e-6)
    assert recs[0]["flags"] == ["duplicate_source_id"] and recs[1]["flags"] == ["duplicate_source_id"]
    assert recs[2]["flags"] == ["undated"] and recs[3]["flags"] == ["undated"]


def test_identical_bytes_under_one_id_is_not_a_conflict():
    a = _rec(1, source_id="X"); b = _rec(1, source_id="X")  # same content, same id: an exact duplicate, not an id defect
    res = {r.metric_id: r.value for r in ProvenanceAnalyzer().corpus([a, b])}
    assert res["prov.duplicate_id_count"] == 0 and res["prov.duplicate_id_rate"] == 0.0


def test_no_ids_means_rate_undefined_and_no_dates_means_no_range():
    res = {r.metric_id: r.value for r in ProvenanceAnalyzer().corpus([_rec(1), _rec(2)])}
    assert res["prov.duplicate_id_count"] == 0 and res["prov.duplicate_id_rate"] is None
    assert res["prov.date_range"] is None and res["prov.undated_rate"] == 1.0


def test_empty_corpus():
    res = {r.metric_id: r.value for r in ProvenanceAnalyzer().corpus([])}
    assert res["prov.undated_rate"] == 0.0 and res["prov.source_histogram"] == {} and res["prov.reliability_histogram"] == {"unrated": 0}


# fixture with sidecar, end to end

def test_fixture_provenance(corpus, signer):
    m = _scan(corpus, signer)
    res = _results(m)
    assert res["prov.source_histogram"]["records-mgmt"] == {"docs": 4, "bytes": 1476}
    assert res["prov.date_range"] == {"min": "2026-04-12T09:15:00Z", "max": "2026-06-03T07:00:00Z", "dated": 12}
    assert res["prov.undated_rate"] == pytest.approx(2 / 14, abs=1e-6)
    assert res["prov.custody_complete_rate"] == 0.5
    assert res["prov.reliability_histogram"] == {"A1": 1, "A2": 3, "B2": 2, "B3": 1, "unrated": 7}
    assert res["prov.derived_share"] == pytest.approx(1 / 14, abs=1e-6)
    assert res["prov.duplicate_id_count"] == 2 and res["prov.duplicate_id_rate"] == pytest.approx(2 / 10, abs=1e-6)
    recs = _records(corpus)
    assert "undated" in recs["short-09.txt"]["flags"] and "undated" in recs["mixed-10.txt"]["flags"]
    assert recs["report-11.txt"]["flags"] == ["duplicate_source_id", "near_duplicate"]
    assert recs["memo-01.txt"]["flags"] == ["exact_duplicate"]  # distinct ids, so no id conflict
    assert recs["bulletin-12-copy.txt"]["envelope"]["parent_hash"] == recs["bulletin-12.txt"]["doc_hash"]


def test_fixture_findings(corpus, signer):
    m = _scan(corpus, signer)
    f = {x["finding_id"]: x for x in m["findings"]}
    assert f["PROV-001"]["status"] == "flag" and f["PROV-001"]["severity"] == "low"
    assert {e["doc_hash"] for e in f["PROV-001"]["evidence"]} == {_records(corpus)[n]["doc_hash"] for n in ("short-09.txt", "mixed-10.txt")}
    assert f["PROV-002"]["status"] == "fail" and f["PROV-002"]["severity"] == "high"
    assert {e["doc_hash"] for e in f["PROV-002"]["evidence"]} == {_records(corpus)[n]["doc_hash"] for n in ("report-11.txt", "report-11-rev2.txt")}


def test_without_sidecar_everything_is_undated_and_ids_are_inconclusive(corpus, signer):
    m = _scan(corpus, signer, provenance=None)
    f = {x["finding_id"]: x for x in m["findings"]}
    assert _results(m)["prov.undated_rate"] == 1.0 and _results(m)["prov.date_range"] is None
    assert f["PROV-001"]["status"] == "fail" and len(f["PROV-001"]["evidence"]) == 13  # 14 docs, one exact-duplicate hash deduped
    assert f["PROV-002"]["status"] == "inconclusive" and "undefined for this corpus" in f["PROV-002"]["gate"]["reason"]
    assert "analyzer:provenance" in m["run"]["pins"]


def test_sidecar_merkle_root_unchanged(corpus, signer):
    """Provenance lives in the envelope, not the bytes: the corpus identity is the same with or without it."""
    assert _scan(corpus, signer)["corpus"]["merkle_root"] == _scan(corpus, signer, provenance=None)["corpus"]["merkle_root"]


# sidecar strictness

def test_sidecar_rejects_unknown_fields(tmp_path):
    p = tmp_path / "p.jsonl"
    p.write_text('{"locator": "memo-01.txt", "collected": "2026-01-01T00:00:00Z"}\n')
    with pytest.raises(ProvenanceError, match="unknown field"):
        load_provenance(p)


def test_sidecar_rejects_unknown_locator(corpus, tmp_path):
    p = tmp_path / "p.jsonl"
    p.write_text('{"locator": "ghost.txt", "source_system": "s"}\n')
    with pytest.raises(ProvenanceError, match="not in the corpus: ghost.txt"):
        list(docs_from_dir(corpus, p))


def test_sidecar_rejects_duplicate_locator_and_bad_json(tmp_path):
    p = tmp_path / "p.jsonl"
    p.write_text('{"locator": "a"}\n{"locator": "a"}\n')
    with pytest.raises(ProvenanceError, match="twice"):
        load_provenance(p)
    p.write_text('{"locator": \n')
    with pytest.raises(ProvenanceError, match="not JSON"):
        load_provenance(p)


def test_sidecar_values_hit_the_envelope_schema(corpus, tmp_path):
    p = tmp_path / "p.jsonl"
    p.write_text('{"locator": "memo-01.txt", "reliability": {"source": "Z"}}\n')
    with pytest.raises(Exception, match="Z"):
        list(docs_from_dir(corpus, p))
