from corpuscle import catalog


def test_catalog_loads_and_ids_unique():
    c = catalog.load()
    ids = [m["id"] for m in c["metrics"]]
    assert len(ids) == len(set(ids))


def test_existing_profiler_is_covered():
    """The existing profiler's 105 metrics, counting mean and var separately, map onto the baseline IDs.
    Textstat 40, spaCy 54, tiktoken 3, language 3+, data health 3, duplicates 2."""
    c = catalog.load()
    base = [m for m in c["metrics"] if m["status"] == "baseline"]
    count = 0
    for m in base:
        aggs = m.get("aggregations")
        count += len([a for a in aggs if a in ("mean", "var")]) if aggs else 1
    assert count == 105


def test_english_readability_is_scoped():
    for m in catalog.load()["metrics"]:
        if m["family"] == "readability" and m["id"].startswith("read.") and "fernandez" not in m["id"] and "szigriszt" not in m["id"]:
            assert m["scope"] == "lang:en"


def test_entity_metrics_never_store_values():
    """Entity density is a count per 1k tokens; nothing in the catalog stores entity text but salient terms, which says so."""
    for m in catalog.load()["metrics"]:
        if m["family"] == "entities":
            assert m["unit"] == "per 1k tokens" and m["scope"] == "lang:en"
    assert "content" in catalog.metric("lex.salient_terms")["note"]
