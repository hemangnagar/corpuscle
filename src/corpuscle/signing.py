"""DSSE envelope over an in-toto Statement whose predicate is the manifest.

Signer is pluggable: v0 ships Ed25519 keys on disk. The government packaging layer
swaps in DoD PKI (X.509 / PIV) behind the same interface; the envelope format does
not change.
"""
from __future__ import annotations
import base64, json
from pathlib import Path
from typing import Protocol
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

PAYLOAD_TYPE = "application/vnd.in-toto+json"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://corpuscle.dev/manifest/v0"


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE pre-authentication encoding."""
    return b"DSSEv1 %d %s %d %s" % (len(payload_type), payload_type.encode(), len(payload), payload)


class Signer(Protocol):
    keyid: str
    def sign(self, data: bytes) -> bytes: ...


class Verifier(Protocol):
    keyid: str
    def verify(self, data: bytes, sig: bytes) -> bool: ...


class Ed25519Signer:
    def __init__(self, key: Ed25519PrivateKey, keyid: str):
        self._key, self.keyid = key, keyid

    @classmethod
    def generate(cls, keyid: str = "dev") -> "Ed25519Signer":
        return cls(Ed25519PrivateKey.generate(), keyid)

    @classmethod
    def from_pem(cls, path, keyid: str) -> "Ed25519Signer":
        key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
        return cls(key, keyid)

    def save_pem(self, priv_path, pub_path) -> None:
        Path(priv_path).write_bytes(self._key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        Path(pub_path).write_bytes(self._key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

    def sign(self, data: bytes) -> bytes:
        return self._key.sign(data)

    def verifier(self) -> "Ed25519Verifier":
        return Ed25519Verifier(self._key.public_key(), self.keyid)


class Ed25519Verifier:
    def __init__(self, key: Ed25519PublicKey, keyid: str):
        self._key, self.keyid = key, keyid

    @classmethod
    def from_pem(cls, path, keyid: str) -> "Ed25519Verifier":
        return cls(serialization.load_pem_public_key(Path(path).read_bytes()), keyid)

    def verify(self, data: bytes, sig: bytes) -> bool:
        try:
            self._key.verify(sig, data)
            return True
        except InvalidSignature:
            return False


def statement(manifest: dict) -> dict:
    return {
        "_type": STATEMENT_TYPE,
        "subject": [{"name": manifest["corpus"]["corpus_id"] + "@" + manifest["corpus"]["version_id"],
                     "digest": {"sha256": manifest["corpus"]["merkle_root"]}}],
        "predicateType": PREDICATE_TYPE,
        "predicate": manifest,
    }


def sign_manifest(manifest: dict, signers: list[Signer]) -> dict:
    payload = canonical(statement(manifest))
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode(),
        "signatures": [{"keyid": s.keyid, "sig": base64.b64encode(s.sign(pae(PAYLOAD_TYPE, payload))).decode()}
                       for s in signers],
    }


def open_envelope(env: dict, verifiers: list[Verifier]) -> dict:
    """Return the statement if at least one signature verifies under a known key; raise otherwise."""
    payload = base64.b64decode(env["payload"])
    data = pae(env["payloadType"], payload)
    by_id = {v.keyid: v for v in verifiers}
    ok = any(by_id[s["keyid"]].verify(data, base64.b64decode(s["sig"]))
             for s in env["signatures"] if s["keyid"] in by_id)
    if not ok:
        raise InvalidSignature("no signature verified under the supplied keys")
    return json.loads(payload)
