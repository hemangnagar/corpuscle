"""corpuscle keygen | scan | verify"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

from .envelope import make_envelope
from .gate import DEFAULT_POLICY, PolicyError
from .manifest import build
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
        print(f"bundle written to {cd}/.corpuscle  root={m['corpus']['merkle_root'][:16]}…  docs={m['corpus']['document_count']}")
        if m["findings"]:
            print(f"policy {m['run']['policy_version']}")
            for f in m["findings"]:
                print(f"  {f['status'].upper():<12} {f['severity']:<8} {f['finding_id']:<8} {f['clause']:<20} {f['gate'].get('reason', '')}")
    elif a.cmd == "verify":
        rep = verify(a.corpus_dir, [Ed25519Verifier.from_pem(a.pub, a.keyid)],
                     corpus_dir=None if a.no_files else a.corpus_dir)
        print(rep)
        sys.exit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
