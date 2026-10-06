"""First analyzer: the two volume metrics. Shows the contract the other 64 follow."""
from __future__ import annotations
from typing import Iterable
from . import Result, register


CHARS_PER_TOKEN = 3.6


def estimate_tokens(text: str) -> int:
    """v0 token estimate; replaced by the tiktoken pin in Phase 2. Other analyzers share it so
    "under 20 tokens" means the same thing everywhere."""
    return max(1, round(len(text) / CHARS_PER_TOKEN)) if text else 0


class VolumeAnalyzer:
    name = "volume"
    version = "0.1.0"
    produces = ("vol.total_docs", "vol.total_tokens", "cnt.token_count")
    pins = {"tokenizer": f"char-estimate/{CHARS_PER_TOKEN}"}  # replaced by tiktoken o200k_base in Phase 1

    def per_document(self, record: dict) -> dict:
        return {"cnt.token_count": estimate_tokens(record.get("text", ""))}

    def corpus(self, records: Iterable[dict]) -> list[Result]:
        n, tokens, per = 0, 0, []
        for r in records:
            n += 1
            t = r.get("metrics", {}).get("cnt.token_count", 0)
            tokens += t
            per.append(t)
        per.sort()
        dist = None
        if per:
            q = lambda p: per[min(len(per) - 1, int(p * (len(per) - 1)))]
            mean = tokens / n
            dist = {"min": per[0], "p5": q(0.05), "p50": q(0.5), "p95": q(0.95), "max": per[-1],
                    "mean": mean, "var": sum((x - mean) ** 2 for x in per) / n}
        return [
            Result("vol.total_docs", self.version, n, unit="docs"),
            Result("vol.total_tokens", self.version, tokens, unit="tokens"),
            Result("cnt.token_count", self.version, None, unit="tokens", distribution=dist),
        ]


register(VolumeAnalyzer())
