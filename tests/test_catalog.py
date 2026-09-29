from corpuscle import catalog


def test_catalog_loads_and_ids_unique():
    c = catalog.load()
    ids = [m["id"] for m in c["metrics"]]
    assert len(ids) == len(set(ids))


def test_baseline_54_is_covered():
    """The existing profiler's 54 metrics, counting mean and var separately, map onto the baseline IDs."""
    c = catalog.load()
    base = [m for m in c["metrics"] if m["status"] == "baseline"]
    count = 0
    for m in base:
        aggs = m.get("aggregations")
        count += len([a for a in aggs if a in ("mean", "var")]) if aggs else 1
    assert count == 54


def test_english_readability_is_scoped():
    for m in catalog.load()["metrics"]:
        if m["family"] == "readability" and m["id"].startswith("read.") and "fernandez" not in m["id"] and "szigriszt" not in m["id"]:
            assert m["scope"] == "lang:en"
