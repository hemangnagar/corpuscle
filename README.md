# corpuscle

An agentic corpus datasheet. Agents plan the scan, investigate the findings, and brief the
authorizing official — on top of a deterministic, signed measurement core. The signed bundle
is the only artifact that leaves the core, and it travels with the corpus.

## Positioning

Corpuscle is not a data quality tool. It is evidence.

A model can improve a corpus. It cannot attest to one. A model's judgment is not reproducible,
not signable, and not something an authorizing official can put their name on. Corpuscle produces
the artifact that question demands: what was in the corpus, who measured it, with which pinned
methods, and whether anyone has changed it since.

The objection this design is built for is "the model will take care of data quality in each use case."

- **Agreed, and Corpuscle is what makes that auditable.** Agents plan scans and investigate
  findings; the deterministic core computes and signs; every agent run is recorded in the manifest
  beside the metrics. Bring your own agent. We sign what it did.
- **The buyer is the signer, not the use-case owner.** The authorizing official, the ISSM, the data
  steward and the CDO cannot answer an AI inventory review or an inspector general with a chat
  transcript. The bundle is their artifact.
- **Measured once, trusted everywhere.** A corpus assessed by each use case's own model is paid for
  per program, with no shared evidence. A signed bundle travels with the corpus, its subsets and
  its derivatives.
- **Lead with what a model cannot see about itself.** Marking ceiling breaches, redaction residue,
  USP indicators, undated documents, and the near-duplicate rate that silently degrades retrieval.
  Readability is the last thing shown, not the first. The roadmap below is ordered accordingly.
- **The verifier is the wedge.** No server, no network, no procurement: a directory, its bundle and
  a public key.

## What is in this commit (Phase 0)

The schemas that everything else writes to, and the smallest test that proves the architecture.

| Path | What |
|---|---|
| `schemas/manifest.schema.json` | Corpus-level statement: identity (Merkle root), run pins, results, findings, agent runs |
| `schemas/record.schema.json` | Per-document record, keyed by content hash. Categories and counts only, never PII values |
| `schemas/provenance-envelope.schema.json` | What every connector must capture at ingest |
| `catalog/metric-catalog.yaml` | 66 metric IDs across nine families with method versions and detector pins; the existing 54 map onto the `baseline` IDs |
| `api/openapi.yaml` | Resource model and async job pattern; MCP mirrors it one-to-one |
| `src/corpuscle/` | Hashing and Merkle proofs, envelope validation, analyzer contract, bundle builder, DSSE signing over an in-toto Statement, offline verifier, CLI |
| `tests/` | Ten-document round trip: build, sign, verify; tamper a document, the records, the manifest; wrong key; single-document Merkle proof; derived subset |

## Try it

```bash
pip install -e ".[dev]"
pytest -q
corpuscle keygen --out keys
corpuscle scan tests/fixtures/sample_corpus --corpus-id sample --version-id v1 --key keys/dev.key.pem
corpuscle verify tests/fixtures/sample_corpus --pub keys/dev.pub.pem
```

`verify` needs no server and no network: a directory, its `.corpuscle/` bundle, and a public key.

## Bundle layout

```
<corpus>/.corpuscle/
  records.jsonl        one record per document, sorted by doc_hash
  manifest.json        unsigned copy, plain JSON for humans and cross-domain guards
  manifest.dsse.json   DSSE envelope over an in-toto Statement; subject = Merkle root
```

## Design rules this code enforces

- **Agents propose, the core disposes.** Nothing in `src/corpuscle` calls a model. Proposals arrive through the API and require an approver before anything executes; agent runs are recorded in the manifest and signed with the metrics.
- **Every number is reproducible.** Analyzer versions and detector pins are recorded per run. A parser or detector upgrade produces a new method version, never a silent change.
- **Records are keyed by content hash**, so they survive renames, moves, subsets and transfers.
- **Signing is pluggable.** Ed25519 on disk for development; DoD PKI behind the same `Signer` interface in the packaging layer.
- **Plain JSON everywhere** so the bundle passes guards that whitelist by schema.

## Roadmap

| Phase | Deliverable |
|---|---|
| 0 | This commit: schemas, catalog, API spec, round-trip test |
| 1 | Plaintext, Office, PDF, email and XML adapters; PySpark runner (local mode for small corpora); banner and portion-mark parser; language, duplication, integrity, compliance and provenance families; finding gate; report renderer |
| 2 | Descriptive, lexical and readability families (the `baseline` continuity set); framework mapping and policy |
| 3 | Agent layer (scan planner, triage investigator, report author) over REST and MCP; proposals and approvals |
| 4 | Government packaging: OpenTDF transfer package, DoD PKI signer, ISM marking parser, offline install bundle |
