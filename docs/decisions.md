# Architecture decisions

| # | Decision | Chosen | Why |
|---|---|---|---|
| 1 | Execution engine | PySpark with local mode | Enterprise and government corpora are terabytes; retrofitting distribution into a metric engine is the rewrite that stalls Phase 3 |
| 2 | Corpus identity | Merkle root over sorted SHA-256 document hashes | Order-independent; single-document membership proofs; subsets and derivatives verify on their own |
| 3 | Signing envelope | DSSE over an in-toto Statement v1 | Mature tooling, same semantics as SLSA attestations, pluggable signers |
| 4 | Records keyed by content hash | yes | Survive renames, moves, transfers and subsetting |
| 5 | v0 detector pins | GlotLID 3.0, datasketch MinHash 128/5-gram/0.8, textstat 0.7.4, Presidio 2.2.358 + en_core_web_lg, ftfy 6.3.1, tiktoken o200k_base | Each changes the numbers; each is recorded per run |
| 6 | The existing 54 metrics | Reimplemented from open components, kept as `baseline` IDs, with English readability scoped to the English slice and MTLD added beside TTR | Continuity for reviewers; corrected methods are defensible in front of an auditor |
| 7 | Bundle format | Plain JSON and JSON Lines, detached signatures | Passes cross-domain guards that whitelist by schema |
| 8 | Agents | Never compute a number, never write to the bundle; every action logged into `agent_runs` | Reproducibility and audit cover the agents, not only the metrics |
