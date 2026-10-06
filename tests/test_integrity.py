"""Integrity family on a deliberately damaged corpus, plus the sample corpus it should mostly pass."""
import json, shutil
from pathlib import Path
import pytest

from corpuscle.adapters.fs import docs_from_dir
from corpuscle.analyzers import integrity as I
from corpuscle.manifest import BUNDLE_DIR, build
from corpuscle.signing import Ed25519Signer

DAMAGED = Path(__file__).parent / "fixtures" / "damaged_corpus"
SAMPLE = Path(__file__).parent / "fixtures" / "sample_corpus"


@pytest.fixture
def signer():
    return Ed25519Signer.generate("test")


def _scan(src, tmp_path, signer, name="c"):
    dst = tmp_path / name
    shutil.copytree(src, dst)
    m = build(dst, corpus_id=name, version_id="v1", docs=list(docs_from_dir(dst)), signers=[signer])
    recs = {r["envelope"]["source_locator"]: r for r in map(json.loads, (dst / BUNDLE_DIR / "records.jsonl").read_text().splitlines())}
    return m, recs


# heuristics, one at a time

def test_mojibake_detection():
    assert I.is_mojibake("The teamâ€™s report")
    assert not I.is_mojibake("The team’s report")
    assert not I.is_mojibake("naïve café — fine as is")


def test_control_chars():
    assert I.has_control_chars("a\x07b") and I.has_control_chars("lost�byte")
    assert not I.has_control_chars("tabs\tand\nnewlines\r\n are whitespace")


def test_markup_residue():
    assert I.has_markup("<p>hi</p>") and I.has_markup("a&nbsp;b") and I.has_markup("<br/>")
    assert not I.has_markup("if a < b and b > c then") and not I.has_markup("AT&T")


def test_boilerplate_share_and_repetition():
    text = "Page 1 of 3\nCONFIDENTIAL\nA real sentence with several words in it.\nA real sentence with several words in it.\nAll rights reserved.\nDo not forward.\n"
    assert I.boilerplate_share(text) == pytest.approx(4 / 6, abs=1e-6)
    assert I.intra_doc_repetition(text) == pytest.approx(1 / 6, abs=1e-6)
    assert I.boilerplate_share("One long single line that is itself the content of the document.") == 0.0
    assert I.intra_doc_repetition("same\nSAME\n  same ") == pytest.approx(2 / 3, abs=1e-6)  # normalized


def test_ngram_repetition():
    assert I.ngram_repetition("alpha beta gamma delta") == 0.0
    assert I.ngram_repetition("alpha beta alpha beta") == 1.0  # every word sits in a repeated bigram
    assert I.ngram_repetition("") == 0.0
    r = I.ngram_repetition("one two three four five six one two")
    assert 0 < r < 1


# the damaged corpus end to end

def test_damaged_corpus_rates_and_flags(tmp_path, signer):
    m, recs = _scan(DAMAGED, tmp_path, signer, "damaged")
    res = {r["metric_id"]: r for r in m["results"]}
    assert m["corpus"]["document_count"] == 7
    for k, v in {"int.empty_count": 1, "int.empty_rate": 1 / 7, "int.near_empty_rate": 1 / 7, "int.truncation_rate": 1 / 7,
                 "int.mojibake_rate": 1 / 7, "int.control_char_rate": 1 / 7, "int.markup_residue_rate": 1 / 7,
                 "int.large_count": 0, "int.large_rate": 0.0}.items():
        assert res[k]["value"] == pytest.approx(v, abs=1e-6), k
    assert res["int.boilerplate_share"]["distribution"]["max"] == pytest.approx(4 / 6, abs=1e-6)
    assert res["int.intra_doc_repetition"]["distribution"]["max"] == pytest.approx(1 / 6, abs=1e-6)
    assert res["int.ngram_repetition"]["distribution"]["max"] > 0.7
    strip = lambda n: [f for f in recs[n]["flags"] if f not in ("undated", "unmarked")]
    assert strip("empty.txt") == ["empty", "near_empty"]
    assert strip("mojibake.txt") == ["mojibake"]
    assert strip("control.txt") == ["control_chars"]
    assert strip("markup.txt") == ["markup_residue"]          # ends in </div>, which is not truncation
    assert strip("truncated.txt") == ["truncated"]
    assert strip("boilerplate.txt") == [] and strip("clean.txt") == []
    assert recs["boilerplate.txt"]["metrics"]["int.boilerplate_share"] == pytest.approx(4 / 6, abs=1e-6)
    assert not any(k.startswith("_") for r in recs.values() for k in r["metrics"])


def test_damaged_corpus_findings(tmp_path, signer):
    m, recs = _scan(DAMAGED, tmp_path, signer, "damaged")
    f = {x["finding_id"]: x for x in m["findings"]}
    assert f["INT-001"]["status"] == "fail" and [e["doc_hash"] for e in f["INT-001"]["evidence"]] == [recs["empty.txt"]["doc_hash"]]
    assert f["INT-002"]["status"] == "fail" and f["INT-002"]["evidence"][0]["doc_hash"] == recs["mojibake.txt"]["doc_hash"]
    assert f["INT-003"]["status"] == "fail" and f["INT-003"]["evidence"][0]["doc_hash"] == recs["control.txt"]["doc_hash"]
    assert f["INT-004"]["status"] == "flag" and f["INT-005"]["status"] == "flag" and f["INT-006"]["status"] == "flag"
    assert f["INT-005"]["evidence"][0]["doc_hash"] == recs["truncated.txt"]["doc_hash"]
    assert m["run"]["pins"]["ftfy"] and m["run"]["pins"]["integrity"].startswith("near_empty<20tok")


def test_large_threshold_is_a_parameter(tmp_path):
    an = I.IntegrityAnalyzer(large_bytes=100)
    rec = {"text": "x" * 150, "envelope": {"size_bytes": 150}}
    assert "large" in an.per_document(rec)["_int.flags"]
    assert "large" not in I.IntegrityAnalyzer().per_document(rec)["_int.flags"]
    assert "large>100B" in an.pins["integrity"]


def test_sample_corpus_is_mostly_clean(tmp_path, signer):
    m, recs = _scan(SAMPLE, tmp_path, signer, "sample")
    f = {x["finding_id"]: x["status"] for x in m["findings"]}
    assert f["INT-001"] == "pass" and f["INT-002"] == "pass" and f["INT-003"] == "pass" and f["INT-006"] == "pass"
    assert f["INT-004"] == "flag"   # short-09.txt is one word
    assert f["INT-005"] == "pass"   # log-08.txt ends without punctuation but 1/14 is under the flag line
    assert "near_empty" in recs["short-09.txt"]["flags"] and "truncated" in recs["log-08.txt"]["flags"]
