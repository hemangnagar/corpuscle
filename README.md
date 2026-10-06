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

## What is in the repo

Phase 0: the schemas that everything else writes to, and the smallest test that proves the architecture.
Phase 1, first slice: the duplication family and the finding gate, so a scan ends in a signed finding.
Phase 3, first slice: the triage investigator, a proposal store and approval, so an agent's work is signed beside the numbers. See [docs/architecture.md](docs/architecture.md).

| Path | What |
|---|---|
| `schemas/manifest.schema.json` | Corpus-level statement: identity (Merkle root), run pins, results, findings, agent runs |
| `schemas/record.schema.json` | Per-document record, keyed by content hash. Categories and counts only, never PII values |
| `schemas/provenance-envelope.schema.json` | What every connector must capture at ingest |
| `catalog/metric-catalog.yaml` | 97 metric IDs across ten families with method versions and detector pins; the existing profiler's 105 metrics map onto the `baseline` IDs |
| `schemas/policy.schema.json`, `policy/default.yaml` | Finding policy: which measured values count as a finding, under which clause, at which severity. Its id, version and content hash travel in the signed manifest |
| `api/openapi.yaml` | Resource model and async job pattern; MCP mirrors it one-to-one |
| `src/corpuscle/` | Hashing and Merkle proofs, envelope validation, analyzer contract, bundle builder, finding gate, DSSE signing over an in-toto Statement, offline verifier, CLI |
| `src/corpuscle/tools.py`, `src/corpuscle/proposals.py` | The tool surface agents investigate through (every call hashed into the log; the only write is `propose`) and the proposal store with named approval, which amends and re-signs the manifest |
| `src/corpuscle_agents/` | The agent layer, the only code that calls a model. Triage investigator over the Anthropic SDK, plus a scripted model for tests and offline demos |
| `src/corpuscle/analyzers/duplication.py` | Exact duplicates from the content hash; near duplicates by MinHash (128 perms, 5-word shingles) with a recall-weighted LSH candidate net confirmed at the 0.8 threshold |
| `tests/` | Fourteen-document round trip: build, sign, verify; tamper a document, the records, the manifest; wrong key; single-document Merkle proof; derived subset. Gate: findings land in the signed manifest with the flagged documents as evidence, pass on a clean subset, go inconclusive when a metric is missing, and are deterministic |

## Try it

```bash
pip install -e ".[dev]"            # Python 3.10+; on Windows, `py -3.11 -m venv .venv` if `py` defaults to an older interpreter
pytest -q
corpuscle keygen --out keys
corpuscle scan tests/fixtures/sample_corpus --corpus-id sample --version-id v1 --key keys/dev.key.pem
corpuscle verify tests/fixtures/sample_corpus --pub keys/dev.pub.pem
```

The fixture corpus carries one exact pair and two near pairs, so the scan ends in two findings:

```
policy corpuscle-default/0.1.0
  FAIL         medium   DUP-001  duplication.exact    0.142857 fraction > 0.1
  FAIL         high     DUP-002  duplication.near     0.285714 fraction > 0.1
```

Each finding names its rule, clause, observed value, threshold and the documents behind it, and is
inside the signed statement. `--policy` points at another policy file; `--no-policy` measures only.

`verify` needs no server and no network: a directory, its `.corpuscle/` bundle, and a public key.

### Let an agent investigate

```bash
pip install -e ".[agents]"        # the Anthropic SDK
export CORPUSCLE_ANTHROPIC_KEY=…  # or ANTHROPIC_API_KEY, or `ant auth login`; see note below
corpuscle triage tests/fixtures/sample_corpus --finding DUP-002
corpuscle proposals tests/fixtures/sample_corpus
corpuscle approve tests/fixtures/sample_corpus prop-… --approver "Dana Reyes, ISSM" --key keys/dev.key.pem
corpuscle verify tests/fixtures/sample_corpus --pub keys/dev.pub.pem
```

The investigator reads the finding, diffs the evidence, and proposes an assessment (real, artifact
or inconclusive) with a narrative and a remediation. Nothing changes until a named approver accepts
it; then the finding gains the assessment and the approver's identity, the agent's run (every tool
call, hashed) is appended to `agent_runs`, and the manifest is re-signed. The observed value, the
threshold, the verdict, the records and the Merkle root do not move.

Credentials: `CORPUSCLE_ANTHROPIC_KEY` is read first and sends the agent straight to
`api.anthropic.com` (override with `CORPUSCLE_ANTHROPIC_BASE_URL`). Some hosted sandboxes refuse
to pass a variable named `ANTHROPIC_API_KEY` into a session and set `ANTHROPIC_BASE_URL` to their
own proxy; the project-specific name sidesteps both. Without it, the SDK's usual resolution applies.

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
- **Every finding is reproducible.** The policy is not the pipeline configuration: what ran is in `run.pins`, what counts is in the policy, and the policy's id, version and content hash are signed beside the results. A metric the run did not report yields an inconclusive finding, never silence.
- **Records are keyed by content hash**, so they survive renames, moves, subsets and transfers.
- **Signing is pluggable.** Ed25519 on disk for development; DoD PKI behind the same `Signer` interface in the packaging layer.
- **Plain JSON everywhere** so the bundle passes guards that whitelist by schema.

## Roadmap

| Phase | Deliverable |
|---|---|
| 0 | This commit: schemas, catalog, API spec, round-trip test |
| 1 | Plaintext, Office, PDF, email and XML adapters; PySpark runner (local mode for small corpora); banner and portion-mark parser; language, duplication, integrity, compliance and provenance families; finding gate; report renderer |
| 2 | Descriptive, lexical and readability families (the `baseline` continuity set); framework mapping and policy |
| 3 | Agent layer over REST and MCP. Landed: triage investigator, proposals, approval. Next: scan planner, report author, MCP server |
| 4 | Government packaging: OpenTDF transfer package, DoD PKI signer, ISM marking parser, offline install bundle |
