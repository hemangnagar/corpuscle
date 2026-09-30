# Live triage run on DUP-002

Date: 2026-09-30

Corpus: `tests/fixtures/sample_corpus`, corpus id `sample`, version `v1`. Run from the repository root on branch `claude/triage-live-run` (with `main` merged in, so the `datasketch<2` pin and the `CORPUSCLE_ANTHROPIC_KEY` credential path were present) in a fresh virtualenv:

```
python3 -m venv .venv && . .venv/bin/activate && pip install -q -e ".[dev,agents]"
```

The install resolved `anthropic` 1.9.0 and `datasketch` 1.10.0. The triage agent ran with the default model (`claude-opus-5-5`, effort `medium`, server-side fallbacks on) and made live calls to the Anthropic API. No repository file was changed by the run and `corpuscle approve` was not run; the proposal below is still `pending`.

## Step 2: credential presence check

```
$ python -c "import os; print('CORPUSCLE_ANTHROPIC_KEY set:', bool(os.environ.get('CORPUSCLE_ANTHROPIC_KEY')))"
CORPUSCLE_ANTHROPIC_KEY set: True
```

## Step 4: `corpuscle scan tests/fixtures/sample_corpus --corpus-id sample --version-id v1 --key keys/dev.key.pem`

Exit code 0. Combined stdout and stderr:

```
bundle written to tests/fixtures/sample_corpus/.corpuscle  root=d0ad149212ec3606…  docs=14
policy corpuscle-default/0.1.0
  FAIL         medium   DUP-001  duplication.exact    0.142857 fraction > 0.1
  FAIL         high     DUP-002  duplication.near     0.285714 fraction > 0.1
```

## Step 5: `corpuscle triage tests/fixtures/sample_corpus --finding DUP-002`

Exit code 0. Combined stdout and stderr:

```
proposal prop-e1e8af0bd5cb  pending  by triage-investigator / claude-opus-5-5
  finding     DUP-002
  assessment  real
  narrative   The four flagged documents are two pairs of near-copies. bulletin-12.txt (78e43622…) and bulletin-12-copy.txt (08199003…) differ by one phrase, and report-11.txt (6ccdc036…) and report-11-rev2.txt (e09cf6d2…) differ by one word. These are redundant copies and revisions of the same content, not distinct documents, so they over-weight two items in a 14-document sample. One more point: the bulletin copy gives a different count ("twice" vs "three times"), so a data owner should decide which version is correct before either one is removed.
  remediation Keep one authoritative version of each pair (likely report-11-rev2.txt, and whichever bulletin-12 version the data owner confirms), take the other out of the corpus, and have the core re-measure.  ->  With no near-duplicate pairs left among these documents, dup.near_rate should drop to zero or close to it, below both the flag and fail thresholds. The core's re-measurement needs to confirm this.
  evidence    78e43622743c, 08199003842a, 6ccdc03669cc, e09cf6d21548
  tool calls  8: get_finding, get_record, get_record, get_record, get_record, diff_documents, diff_documents, propose
  nothing changes until: corpuscle approve <corpus> prop-e1e8af0bd5cb --approver <name> --key <pem>
```

## Step 6: `corpuscle proposals tests/fixtures/sample_corpus`

Exit code 0. Combined stdout and stderr:

```
prop-e1e8af0bd5cb  pending   DUP-002  real          triage-investigator / claude-opus-5-5
```

## Proposal files

Every file under `tests/fixtures/sample_corpus/.corpuscle/proposals/` after the run (1 file):

```json
// tests/fixtures/sample_corpus/.corpuscle/proposals/prop-e1e8af0bd5cb.json
{
  "agent": "triage-investigator",
  "agent_run": {
    "agent": "triage-investigator",
    "conclusion": "The four flagged documents are two pairs of near-copies. bulletin-12.txt (78e43622…) and bulletin-12-copy.txt (08199003…) differ by one phrase, and report-11.txt (6ccdc036…) and report-11-rev2.txt (e09cf6d2…) differ by one word. These are redundant copies and revisions of the same content, not distinct documents, so they over-weight two items in a 14-document sample. One more point: the bulletin copy gives a different count (\"twice\" vs \"three times\"), so a data owner should decide which version is correct before either one is removed.",
    "finished_at": "2026-09-30T16:20:28Z",
    "model": "claude-opus-5-5",
    "started_at": "2026-09-30T16:20:02Z",
    "tool_calls": [
      {
        "args_hash": "1eb2360a6499ae90f51049405efa5629060f73710046425ecfb974f009fdeba4",
        "result_hash": "6a1bd0c3dad9f82951f0da46ff78bbff18f87921b90b72e0819ae2f485669df5",
        "tool": "get_finding"
      },
      {
        "args_hash": "f70f4bbf6e4bbfdfc3b66e0b54980fd229f5693919bfa170f8b0a686866094a3",
        "result_hash": "0b8a80bc1bf2cf9d293dcd4a368fad93fb4b73361bfbd041ab0b95d941547462",
        "tool": "get_record"
      },
      {
        "args_hash": "c6da2466f335dfb0d538624fd351bfc12912b7d6b17558b5a3101d7dae335df7",
        "result_hash": "ed61ff82a94561b71f5b0ed40b47a8f5170ee377186861a842bafa1c1490565d",
        "tool": "get_record"
      },
      {
        "args_hash": "eab2a315cdca8d1ffd308ec75766cf537949928e4330136d607b1abaf77c62c8",
        "result_hash": "5a498f8bc5158fc8525e3c0a641283fa58a5cdea6099cb0c23fe1b133f07639d",
        "tool": "get_record"
      },
      {
        "args_hash": "7be4898bbe272e00130c650ff5cf967265151bcbb8efa2de0ead32cd3fd5c2bf",
        "result_hash": "7cf2784f891e1a92aaa9ea8e02b1a91c1bb2abead22f5fcf9de5ce440b585508",
        "tool": "get_record"
      },
      {
        "args_hash": "cf0a4fc934a9a4504e4c78bcae1d26cd1618d9216baef794a9b4fede5a676c22",
        "result_hash": "f7bf57c5557372d2e0886e397b1d6e0f56e3bc2a3430c4a5e7f58dd8032e3460",
        "tool": "diff_documents"
      },
      {
        "args_hash": "deabdaba4eede09d81170a5e53995835bd9b898ed271313262d010e93a4abcee",
        "result_hash": "fda8eb93b557049650bdfd14865b6da05cc02b9461baac69424fa506b78a9183",
        "tool": "diff_documents"
      },
      {
        "args_hash": "59ff64be3a5b1ae9d5ef55b960d7a5dcf5f5c3269bc68c5845e66214e9db9aa1",
        "result_hash": "27f5f92463b5942ac2f2f1c21c601f362fe3f0142a92a5e3b39fe448db6261a4",
        "tool": "propose"
      }
    ]
  },
  "evidence": [
    {
      "doc_hash": "78e43622743c72adcacebcda9c36c5d4fab029569890cffb09d4984aa7d5f968"
    },
    {
      "doc_hash": "08199003842aed923acdfcbf4bf114d8680c74fb73c8e499c94ff470070b78f9"
    },
    {
      "doc_hash": "6ccdc03669ccbf33b556810fec75e93d7030e6c8ddf69d3c5fdd8a921539c6bc"
    },
    {
      "doc_hash": "e09cf6d21548a175906579416bd0a7822b141ad0eeee12c17d652eaeafdc326b"
    }
  ],
  "kind": "finding",
  "model": "claude-opus-5-5",
  "payload": {
    "assessment": "real",
    "finding_id": "DUP-002",
    "narrative": "The four flagged documents are two pairs of near-copies. bulletin-12.txt (78e43622…) and bulletin-12-copy.txt (08199003…) differ by one phrase, and report-11.txt (6ccdc036…) and report-11-rev2.txt (e09cf6d2…) differ by one word. These are redundant copies and revisions of the same content, not distinct documents, so they over-weight two items in a 14-document sample. One more point: the bulletin copy gives a different count (\"twice\" vs \"three times\"), so a data owner should decide which version is correct before either one is removed.",
    "remediation": {
      "action": "Keep one authoritative version of each pair (likely report-11-rev2.txt, and whichever bulletin-12 version the data owner confirms), take the other out of the corpus, and have the core re-measure.",
      "predicted_effect": "With no near-duplicate pairs left among these documents, dup.near_rate should drop to zero or close to it, below both the flag and fail thresholds. The core's re-measurement needs to confirm this."
    }
  },
  "proposal_id": "prop-e1e8af0bd5cb",
  "status": "pending",
  "submitted_at": "2026-09-30T16:20:28Z"
}
```

## Agent run tool calls

Proposal `prop-e1e8af0bd5cb`: agent `triage-investigator`, model `claude-opus-5-5`, started 2026-09-30T16:20:02Z, finished 2026-09-30T16:20:28Z, 8 tool calls. Arguments and results are stored as SHA-256 hashes only, so document text never enters the record.

| # | tool | args_hash | result_hash |
|---|------|-----------|-------------|
| 1 | `get_finding` | `1eb2360a6499ae90f51049405efa5629060f73710046425ecfb974f009fdeba4` | `6a1bd0c3dad9f82951f0da46ff78bbff18f87921b90b72e0819ae2f485669df5` |
| 2 | `get_record` | `f70f4bbf6e4bbfdfc3b66e0b54980fd229f5693919bfa170f8b0a686866094a3` | `0b8a80bc1bf2cf9d293dcd4a368fad93fb4b73361bfbd041ab0b95d941547462` |
| 3 | `get_record` | `c6da2466f335dfb0d538624fd351bfc12912b7d6b17558b5a3101d7dae335df7` | `ed61ff82a94561b71f5b0ed40b47a8f5170ee377186861a842bafa1c1490565d` |
| 4 | `get_record` | `eab2a315cdca8d1ffd308ec75766cf537949928e4330136d607b1abaf77c62c8` | `5a498f8bc5158fc8525e3c0a641283fa58a5cdea6099cb0c23fe1b133f07639d` |
| 5 | `get_record` | `7be4898bbe272e00130c650ff5cf967265151bcbb8efa2de0ead32cd3fd5c2bf` | `7cf2784f891e1a92aaa9ea8e02b1a91c1bb2abead22f5fcf9de5ce440b585508` |
| 6 | `diff_documents` | `cf0a4fc934a9a4504e4c78bcae1d26cd1618d9216baef794a9b4fede5a676c22` | `f7bf57c5557372d2e0886e397b1d6e0f56e3bc2a3430c4a5e7f58dd8032e3460` |
| 7 | `diff_documents` | `deabdaba4eede09d81170a5e53995835bd9b898ed271313262d010e93a4abcee` | `fda8eb93b557049650bdfd14865b6da05cc02b9461baac69424fa506b78a9183` |
| 8 | `propose` | `59ff64be3a5b1ae9d5ef55b960d7a5dcf5f5c3269bc68c5845e66214e9db9aa1` | `27f5f92463b5942ac2f2f1c21c601f362fe3f0142a92a5e3b39fe448db6261a4` |

## Approval

The proposal was approved from the parent session with the same proposal JSON placed beside a fresh scan of the same corpus (identical Merkle root `d0ad149212ec3606…` and identical findings), then verified offline.

```
$ corpuscle approve live prop-e1e8af0bd5cb --approver "Hemang Nagar (approved via Claude Code)" --key keys/dev.key.pem
approved prop-e1e8af0bd5cb by Hemang Nagar (approved via Claude Code); manifest re-signed
  DUP-002 fail high  assessment=real  agent_runs=1

$ corpuscle verify live --pub keys/dev.pub.pem
PASS  signature
PASS  manifest schema
PASS  records hash
PASS  records count
PASS  merkle root
PASS  statement subject
PASS  corpus files match records
RESULT  verified
```

The finding DUP-002 in the re-signed manifest:

```json
{
 "finding_id": "DUP-002",
 "status": "fail",
 "severity": "high",
 "observed": 0.285714,
 "threshold": {
  "fail": {
   "op": ">",
   "value": 0.1
  },
  "flag": {
   "op": ">",
   "value": 0.02
  }
 },
 "assessment": "real",
 "approved_by": "Hemang Nagar (approved via Claude Code)",
 "approved_at": "2026-09-30T16:28:51Z",
 "remediation": {
  "action": "Keep one authoritative version of each pair (likely report-11-rev2.txt, and whichever bulletin-12 version the data owner confirms), take the other out of the corpus, and have the core re-measure.",
  "predicted_effect": "With no near-duplicate pairs left among these documents, dup.near_rate should drop to zero or close to it, below both the flag and fail thresholds. The core's re-measurement needs to confirm this."
 }
}
```

`agent_runs` holds one entry: `triage-investigator` on `claude-opus-5-5`, eight hashed tool calls, proposal `prop-e1e8af0bd5cb`. Observed value, threshold, status, severity, results, records and Merkle root are unchanged from the original scan.
