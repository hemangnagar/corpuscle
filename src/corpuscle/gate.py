"""Finding gate: a policy turns measured results into findings.

The policy is not the pipeline configuration. Which analyzers ran and with which pins is
recorded in manifest.run; the policy says which measured values count as a finding, under
which framework clause, at which severity. Both travel in the signed manifest: the policy's
id and version in run.policy_version, its content hash in run.pins, so a finding can be
regenerated exactly, or disputed exactly, a year later.

A rule names one metric (and scope), an optional flag threshold, an optional fail threshold,
and the severity each carries. Fail is checked first. A metric the run did not report yields
an inconclusive finding rather than silence: an auditor should see that the clause was asked
and not answered.
"""
from __future__ import annotations
import json
import operator
from pathlib import Path
import jsonschema
import yaml

from .envelope import validate
from .hashing import sha256_bytes

POLICY_DIR = Path(__file__).resolve().parents[2] / "policy"
DEFAULT_POLICY = POLICY_DIR / "default.yaml"
EVIDENCE_LIMIT = 50

class PolicyError(ValueError):
    """The policy file is not usable. The message names the file and the offending field."""


_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq, "!=": operator.ne}


def load_policy(path=DEFAULT_POLICY) -> dict:
    """Load and validate a policy file; attach its content hash as _hash (stripped from the manifest)."""
    raw = Path(path).read_bytes()
    policy = yaml.safe_load(raw)
    if not isinstance(policy, dict):
        raise PolicyError(f"{path}: not a policy document")
    for k in ("policy_id", "policy_version"):
        if isinstance(policy.get(k), (int, float)):  # YAML reads 2026.09 or 1.0 as a number
            policy[k] = str(policy[k])
    try:
        validate(policy, "policy.schema.json")
    except jsonschema.ValidationError as e:
        where = "/".join(str(x) for x in e.absolute_path) or "top level"
        raise PolicyError(f"{path}: {e.message} (at {where})") from e
    policy["_hash"] = sha256_bytes(raw)
    return policy


def policy_hash(policy: dict) -> str:
    if "_hash" in policy:
        return policy["_hash"]
    canon = json.dumps({k: v for k, v in policy.items() if not k.startswith("_")}, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(canon.encode())


def policy_version(policy: dict) -> str:
    return f"{policy['policy_id']}/{policy['policy_version']}"


def _hit(value, threshold: dict | None) -> bool:
    return bool(threshold) and _OPS[threshold["op"]](value, threshold["value"])


def evaluate(policy: dict, results: list[dict], records: list[dict]) -> list[dict]:
    """results: manifest-shaped result dicts. records: the records as they will be written."""
    by_key = {(r["metric_id"], r.get("scope", "all")): r for r in results}
    limit = policy.get("evidence_limit", EVIDENCE_LIMIT)
    findings = []
    for rule in policy["rules"]:
        scope = rule.get("scope", "all")
        res = by_key.get((rule["metric_id"], scope))
        thresholds = {k: rule[k] for k in ("flag", "fail") if k in rule}
        f = {
            "finding_id": rule["rule_id"],
            "framework": policy["framework"],
            "clause": rule["clause"],
            "metric_ids": [rule["metric_id"]],
            "threshold": thresholds,
            "gate": {"rule": rule["rule_id"]},
        }
        if res is None or res.get("value") is None:
            f.update(status="inconclusive", severity="none")
            f["gate"].update(verdict="inconclusive", reason=f"{rule['metric_id']} (scope {scope}) not reported in this run")
        else:
            value = res["value"]
            f["observed"] = value
            unit = f" {res['unit']}" if res.get("unit") else ""
            if _hit(value, rule.get("fail")):
                status, sev = "fail", rule["severity"]["fail"]
                reason = f"{value}{unit} {rule['fail']['op']} {rule['fail']['value']}"
            elif _hit(value, rule.get("flag")):
                status, sev = "flag", rule["severity"]["flag"]
                reason = f"{value}{unit} {rule['flag']['op']} {rule['flag']['value']}"
            else:
                status, sev, reason = "pass", "none", f"{value}{unit} within policy"
            f.update(status=status, severity=sev)
            f["gate"].update(verdict=status, reason=reason)
            f["narrative"] = f"{rule['title']}: observed {value}{unit}."
            if status != "pass" and rule.get("evidence_flag"):
                seen, evidence = set(), []
                for r in records:
                    h = r["doc_hash"]
                    if rule["evidence_flag"] in r.get("flags", []) and h not in seen:
                        seen.add(h)
                        evidence.append({"doc_hash": h})
                        if len(evidence) >= limit:
                            break
                if evidence:
                    f["evidence"] = evidence
        findings.append(f)
    return findings
