"""Metric catalog loader. IDs are stable; method versions travel in the manifest."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import yaml

CATALOG_PATH = Path(__file__).resolve().parents[2] / "catalog" / "metric-catalog.yaml"


@lru_cache
def load() -> dict:
    return yaml.safe_load(CATALOG_PATH.read_text())


def metric(metric_id: str) -> dict:
    for m in load()["metrics"]:
        if m["id"] == metric_id:
            return m
    raise KeyError(metric_id)


def version() -> str:
    return load()["catalog_version"]
