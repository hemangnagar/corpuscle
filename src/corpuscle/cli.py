"""corpuscle keygen | scan | verify | triage | proposals | approve | reject"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

from .envelope import make_envelope
from .gate import DEFAULT_POLICY, PolicyError
from . import proposals as store
from .manifest import BUNDLE_DIR, build
from .signing import Ed25519Signer, Ed25519Verifier
from .verify import verify


def _docs_from_dir(corpus_dir: Path):
    for p in sorted(corpus_dir.rglob("*")):
        if p.is_file() and ".corpuscle" not in p.parts:
            data = p.read_bytes()
            env = make_envelope(data, source_system="fs", source_locator=str(p.relative_to(corpus_dir)),
                                adapter_name="plaintext", adapter_version="0.1.0",
                                media_type="text/plain" if p.suffix in (".txt", ".md") else None)
            yield {"envelope": env, "text": data.decode("utf-8", errors="replace")}


def _print_proposal(pr: dict) -> None:
    pay = pr["payload"]
    print(f"proposal {pr['proposal_id']}  {pr['status']}  by {pr['agent']} / {pr['model']}")
    print(f"  finding     {pay['finding_id']}")
    print(f"  assessment  {pay['assessment']}")
    print(f"  narrative   {pay['narrative']}")
    if pay.get("remediation"):
        print(f"  remediation {pay['remediation']['action']}  ->  {pay['remediation']['predicted_effect']}")
    print(f"  evidence    {', '.join(e['doc_hash'][:12] for e in pr['evidence']) or '(none)'}")
    print(f"  tool calls  {len(pr['agent_run']['tool_calls'])}: " + ", ".join(c['tool'] for c in pr['agent_run']['tool_calls']))
    print("  nothing changes until: corpuscle approve <corpus> " + pr["proposal_id"] + " --approver <name> --key <pem>")


def main(argv=None):
    p = argparse.ArgumentParser(prog="corpuscle")
    sub = p.add_subparsers(dest="cmd", required=True)

    k = sub.add_parser("keygen", help="generate a dev Ed25519 keypair")
    k.add_argument("--out", default="keys"); k.add_argument("--keyid", default="dev")

    s = sub.add_parser("scan", help="build and sign a bundle for a directory of documents")
    s.add_argument("corpus_dir"); s.add_argument("--corpus-id", required=True); s.add_argument("--version-id", required=True)
    s.add_argument("--key", required=True, help="private key PEM"); s.add_argument("--keyid", default="dev")
    s.add_argument("--policy", default=None, help="finding policy YAML (default: policy/default.yaml)")
    s.add_argument("--no-policy", action="store_true", help="measure only; write no findings")

    v = sub.add_parser("verify", help="verify a bundle offline against a public key")
    v.add_argument("corpus_dir"); v.add_argument("--pub", required=True); v.add_argument("--keyid", default="dev")
    v.add_argument("--no-files", action="store_true", help="skip per-file hash check (bundle only)")

    t = sub.add_parser("triage", help="run the triage investigator on one finding; writes a proposal, changes nothing")
    t.add_argument("corpus_dir"); t.add_argument("--finding", required=True)
    t.add_argument("--model", default=None, help="model id (default: claude-opus-5-5, or CORPUSCLE_MODEL)")
    t.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    t.add_argument("--no-fallbacks", action="store_true", help="disable server-side refusal fallback")

    pl = sub.add_parser("proposals", help="list proposals beside a bundle")
    pl.add_argument("corpus_dir")

    ap = sub.add_parser("approve", help="approve a proposal with a named identity; amends and re-signs the manifest")
    ap.add_argument("corpus_dir"); ap.add_argument("proposal_id"); ap.add_argument("--approver", required=True)
    ap.add_argument("--key", required=True, help="private key PEM"); ap.add_argument("--keyid", default="dev")

    rj = sub.add_parser("reject", help="reject a proposal")
    rj.add_argument("corpus_dir"); rj.add_argument("proposal_id"); rj.add_argument("--approver", required=True)
    rj.add_argument("--reason", default="")

    a = p.parse_args(argv)
    if a.cmd == "keygen":
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        Ed25519Signer.generate(a.keyid).save_pem(out / f"{a.keyid}.key.pem", out / f"{a.keyid}.pub.pem")
        print(f"wrote {out}/{a.keyid}.key.pem and {out}/{a.keyid}.pub.pem")
    elif a.cmd == "scan":
        cd = Path(a.corpus_dir)
        policy = None if a.no_policy else (a.policy or DEFAULT_POLICY)
        try:
            m = build(cd, corpus_id=a.corpus_id, version_id=a.version_id, docs=list(_docs_from_dir(cd)),
                      signers=[Ed25519Signer.from_pem(a.key, a.keyid)], policy=policy)
        except PolicyError as e:
            sys.exit(f"policy error: {e}")
        print(f"bundle written to {cd / BUNDLE_DIR}  root={m['corpus']['merkle_root'][:16]}…  docs={m['corpus']['document_count']}")
        if m["findings"]:
            print(f"policy {m['run']['policy_version']}")
            for f in m["findings"]:
                print(f"  {f['status'].upper():<12} {f['severity']:<8} {f['finding_id']:<8} {f['clause']:<20} {f['gate'].get('reason', '')}")
    elif a.cmd == "triage":
        from corpuscle_agents.model import AnthropicModel
        from corpuscle_agents.triage import run_triage
        model = AnthropicModel(a.model, effort=a.effort, fallbacks=not a.no_fallbacks)
        try:
            pr = run_triage(a.corpus_dir, a.finding, model)
        except TypeError as e:
            if "authentication" not in str(e).lower():
                raise
            sys.exit("triage: no model credentials. Set CORPUSCLE_ANTHROPIC_KEY (or ANTHROPIC_API_KEY, or run `ant auth login`); "
                     "the agent never runs without them.")
        _print_proposal(pr)
    elif a.cmd == "proposals":
        for pr in store.list_proposals(a.corpus_dir):
            print(f"{pr['proposal_id']}  {pr['status']:<9} {pr['payload']['finding_id']:<8} {pr['payload']['assessment']:<13} {pr['agent']} / {pr['model']}")
    elif a.cmd == "approve":
        try:
            m = store.approve(a.corpus_dir, a.proposal_id, a.approver, [Ed25519Signer.from_pem(a.key, a.keyid)])
        except store.ProposalError as e:
            sys.exit(f"approve: {e}")
        f = next(x for x in m["findings"] if x.get("approved_by") and x["finding_id"] == store.get(a.corpus_dir, a.proposal_id)["payload"]["finding_id"])
        print(f"approved {a.proposal_id} by {a.approver}; manifest re-signed")
        print(f"  {f['finding_id']} {f['status']} {f['severity']}  assessment={f['assessment']}  agent_runs={len(m['agent_runs'])}")
    elif a.cmd == "reject":
        try:
            store.reject(a.corpus_dir, a.proposal_id, a.approver, a.reason)
        except store.ProposalError as e:
            sys.exit(f"reject: {e}")
        print(f"rejected {a.proposal_id} by {a.approver}")
    elif a.cmd == "verify":
        rep = verify(a.corpus_dir, [Ed25519Verifier.from_pem(a.pub, a.keyid)],
                     corpus_dir=None if a.no_files else a.corpus_dir)
        print(rep)
        sys.exit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
