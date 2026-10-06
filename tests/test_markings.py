"""Banner and portion-mark parser, the marking metrics, the run-level ceiling, and the marked-corpus policy."""
import json, shutil
from pathlib import Path
import pytest

from corpuscle import markings as mk
from corpuscle.adapters.fs import docs_from_dir
from corpuscle.analyzers.markings import MarkingAnalyzer
from corpuscle.manifest import BUNDLE_DIR, build
from corpuscle.signing import Ed25519Signer

MARKED = Path(__file__).parent / "fixtures" / "marked_corpus"
SAMPLE = Path(__file__).parent / "fixtures" / "sample_corpus"
POLICY = Path(__file__).parent.parent / "policy" / "marked-corpus.yaml"


@pytest.fixture
def signer():
    return Ed25519Signer.generate("test")


def _scan(src, tmp_path, signer, name="c", **kw):
    dst = tmp_path / name
    shutil.copytree(src, dst)
    m = build(dst, corpus_id=name, version_id="v1", docs=list(docs_from_dir(dst)), signers=[signer], **kw)
    recs = {r["envelope"]["source_locator"]: r for r in map(json.loads, (dst / BUNDLE_DIR / "records.jsonl").read_text().splitlines())}
    return m, recs


# parser

def test_banner_forms():
    assert mk.parse_banner("UNCLASSIFIED") == {"level": "U", "controls": [], "raw": "UNCLASSIFIED"}
    assert mk.parse_banner("  SECRET//NOFORN  ")["controls"] == ["NOFORN"]
    assert mk.parse_banner("TOP SECRET//SI//REL TO USA, FVEY") == {"level": "TS", "controls": ["SI", "REL TO USA, FVEY"], "raw": "TOP SECRET//SI//REL TO USA, FVEY"}
    assert mk.parse_banner("CUI//SP-PRVCY")["level"] == "CUI"
    assert mk.parse_banner("CONTROLLED UNCLASSIFIED INFORMATION")["level"] == "CUI"
    assert mk.parse_banner("The secret is out.") is None          # prose, not a banner
    assert mk.parse_banner("secret//noforn") is None               # lowercase is not a marking
    assert mk.parse_banner("UNCLASSIFIED and more words") is None


def test_portions_and_levels():
    p = mk.parse("UNCLASSIFIED\n\n(U) one.\n\n(S//NF) two.\n\n- (C) three.\n\n1. (TS) four.\n\nUNCLASSIFIED\n")
    assert p["banner"] == "U" and p["banners"] == ["UNCLASSIFIED"]
    assert p["portions"] == {"U": 1, "C": 1, "S": 1, "TS": 1} and p["portion_max"] == "TS"
    assert p["level"] == "TS" and p["marked"] and p["conflict"]


def test_two_banners_at_different_levels_is_a_conflict():
    p = mk.parse("UNCLASSIFIED\n(U) body.\nSECRET\n")
    assert p["banners"] == ["UNCLASSIFIED", "SECRET"] and p["banner"] == "S" and p["conflict"]


def test_source_markings_join_the_banners():
    p = mk.parse("(U) body only.", source_markings=["CUI//SP-PRVCY", "not a marking"])
    assert p["banner"] == "CUI" and p["banners"] == ["CUI//SP-PRVCY"] and p["conflict"]  # CUI banner over U portions


def test_unmarked_and_residue():
    assert mk.parse("Plain prose with the word secret in it.") == {"banner": None, "banners": [], "controls": [], "portions": {},
                                                                   "portion_max": None, "level": None, "marked": False,
                                                                   "conflict": False, "redaction_residue": False}
    assert mk.parse("(U) The complainant, [REDACTED], called.")["redaction_residue"]
    assert mk.parse("(U) Withheld under (b)(6).")["redaction_residue"]
    assert mk.parse("(U) See the SECRET//NOFORN annex.")["redaction_residue"]
    assert mk.parse("(U) Case XXXXXXXX closed.")["redaction_residue"]
    assert not mk.parse("(U) A line of ordinary text with no placeholders.")["redaction_residue"]


def test_level_order_and_ceiling():
    assert [mk.LEVELS[x] for x in ("U", "CUI", "C", "S", "TS")] == [0, 1, 2, 3, 4]
    assert mk.above("CUI", "U") and mk.above("S", "CUI") and not mk.above("U", "U") and not mk.above("TS", "TS")
    assert not mk.above(None, "U") and not mk.above("S", None)


# analyzer and fixture

def test_marked_corpus_with_ceiling(tmp_path, signer):
    m, recs = _scan(MARKED, tmp_path, signer, "marked", analyzer_config={"markings": {"ceiling": "CUI"}})
    res = {r["metric_id"]: r["value"] for r in m["results"]}
    assert res["mark.coverage"] == pytest.approx(6 / 7, abs=1e-6)
    assert res["mark.conflict_rate"] == pytest.approx(1 / 7, abs=1e-6)
    assert res["mark.ceiling_breach"] == 2
    assert res["mark.redaction_residue_rate"] == pytest.approx(2 / 7, abs=1e-6)
    assert m["run"]["pins"]["markings"] == "capco-text/0.1,ceiling=CUI"
    strip = lambda n: [f for f in recs[n]["flags"] if f != "undated"]
    assert strip("status-u.txt") == [] and strip("roster-cui.txt") == []
    assert strip("conflict.txt") == ["ceiling_breach", "marking_conflict"]
    assert strip("annex-s.txt") == ["ceiling_breach"]
    assert strip("redacted.txt") == ["redaction_residue"]
    assert strip("inline-marking.txt") == ["redaction_residue"]
    assert strip("unmarked.txt") == ["unmarked"]
    assert recs["conflict.txt"]["markings_parsed"]["portions"] == {"U": 2, "S": 1}
    assert not any(k.startswith("_") for r in recs.values() for k in r["metrics"])


def test_bottom_banner_is_not_truncation(tmp_path, signer):
    """Every marked fixture ends with its bottom banner, and every one ends a sentence before it."""
    m, recs = _scan(MARKED, tmp_path, signer, "marked")
    assert [n for n, r in sorted(recs.items()) if "truncated" in r["flags"]] == []
    assert {r["metric_id"]: r["value"] for r in m["results"]}["int.truncation_rate"] == 0.0


def test_no_ceiling_means_breach_undefined(tmp_path, signer):
    m, recs = _scan(MARKED, tmp_path, signer, "marked")
    assert {r["metric_id"]: r["value"] for r in m["results"]}["mark.ceiling_breach"] is None
    f = {x["finding_id"]: x for x in m["findings"]}
    assert f["MARK-002"]["status"] == "inconclusive" and "undefined" in f["MARK-002"]["gate"]["reason"]
    assert f["MARK-001"]["status"] == "fail" and f["MARK-003"]["status"] == "fail"
    assert not any("ceiling_breach" in r["flags"] for r in recs.values())
    assert m["run"]["pins"]["markings"].endswith("ceiling=none")


def test_marked_corpus_policy(tmp_path, signer):
    m, recs = _scan(MARKED, tmp_path, signer, "marked", policy=POLICY, analyzer_config={"markings": {"ceiling": "CUI"}})
    f = {x["finding_id"]: x for x in m["findings"]}
    assert m["run"]["policy_version"] == "corpuscle-marked/0.1.0"
    assert f["MARK-000"]["status"] == "fail" and [e["doc_hash"] for e in f["MARK-000"]["evidence"]] == [recs["unmarked.txt"]["doc_hash"]]
    assert f["MARK-001"]["status"] == "fail" and f["MARK-002"]["status"] == "fail" and f["MARK-002"]["severity"] == "critical"
    assert {e["doc_hash"] for e in f["MARK-002"]["evidence"]} == {recs["conflict.txt"]["doc_hash"], recs["annex-s.txt"]["doc_hash"]}
    assert f["MARK-003"]["status"] == "fail" and f["DUP-002"]["status"] == "pass"


def test_ceiling_u_catches_cui(tmp_path, signer):
    m, recs = _scan(MARKED, tmp_path, signer, "marked", analyzer_config={"markings": {"ceiling": "U"}})
    assert {r["metric_id"]: r["value"] for r in m["results"]}["mark.ceiling_breach"] == 3  # roster-cui joins the two secret docs


def test_invalid_ceiling_rejected():
    with pytest.raises(ValueError, match="ceiling must be one of"):
        MarkingAnalyzer(ceiling="SECRET")
    assert MarkingAnalyzer().with_config(ceiling="S").ceiling == "S"


def test_sample_corpus_is_unmarked_and_quiet(tmp_path, signer):
    m, recs = _scan(SAMPLE, tmp_path, signer, "sample")
    res = {r["metric_id"]: r["value"] for r in m["results"]}
    assert res["mark.coverage"] == 0.0 and res["mark.conflict_rate"] == 0.0 and res["mark.redaction_residue_rate"] == 0.0
    f = {x["finding_id"]: x["status"] for x in m["findings"]}
    assert f["MARK-001"] == "pass" and f["MARK-002"] == "inconclusive" and f["MARK-003"] == "pass"
    assert all("unmarked" in r["flags"] for r in recs.values())
