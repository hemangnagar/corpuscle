# Live triage run on DUP-002

Date: 2026-09-30

Corpus: `tests/fixtures/sample_corpus`, corpus id `sample`, version `v1`. Run from the repository root in a fresh virtualenv (`python3 -m venv .venv && pip install -e ".[dev,agents]"`) with a dev key from `corpuscle keygen --out keys`.

## Environment notes

- The unpinned install resolved `datasketch` to 2.0.0, which rejects the `MinHash(num_perm=..., hashvalues=...)` call in the duplication analyzer. The first scan attempt failed with that error (recorded below). The venv was then pinned to `datasketch<2` (1.10.0) and the scan re-run. No repository file was changed.
- `ANTHROPIC_API_KEY` was not set in the execution environment, so the triage agent refused to run. No live model call was made and no proposal was written.

## Step 3: `corpuscle scan tests/fixtures/sample_corpus --corpus-id sample --version-id v1 --key keys/dev.key.pem`

First attempt (datasketch 2.0.0), exit code 1:

```
Traceback (most recent call last):
  File "/home/user/corpuscle/.venv/bin/corpuscle", line 8, in <module>
    sys.exit(main())
             ^^^^^^
  File "/home/user/corpuscle/src/corpuscle/cli.py", line 80, in main
    m = build(cd, corpus_id=a.corpus_id, version_id=a.version_id, docs=list(_docs_from_dir(cd)),
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/corpuscle/src/corpuscle/manifest.py", line 53, in build
    records, results, pins = run_analyzers(docs, analyzers)
                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/corpuscle/src/corpuscle/manifest.py", line 37, in run_analyzers
    results.extend(a.corpus(records))
                   ^^^^^^^^^^^^^^^^^
  File "/home/user/corpuscle/src/corpuscle/analyzers/duplication.py", line 85, in corpus
    reps[h] = MinHash(num_perm=NUM_PERM, hashvalues=hv)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/corpuscle/.venv/lib/python3.11/site-packages/datasketch/minhash.py", line 265, in __init__
    raise ValueError(
ValueError: scheme must be specified explicitly when initializing from existing hash values or permutations: pass the scheme of the MinHash they came from, or scheme='legacy' for values created by datasketch before 2.0.0.
```

Second attempt (datasketch 1.10.0), exit code 0:

```
bundle written to tests/fixtures/sample_corpus/.corpuscle  root=d0ad149212ec3606…  docs=14
policy corpuscle-default/0.1.0
  FAIL         medium   DUP-001  duplication.exact    0.142857 fraction > 0.1
  FAIL         high     DUP-002  duplication.near     0.285714 fraction > 0.1
```

## Step 4: `corpuscle triage tests/fixtures/sample_corpus --finding DUP-002`

Exit code 1, wall time about 2.5 seconds. Complete stdout+stderr:

```
triage: no model credentials. Set ANTHROPIC_API_KEY, or run `ant auth login`; the agent never runs without them.
```

## Step 5: `corpuscle proposals tests/fixtures/sample_corpus`

Exit code 0. Output was empty (no proposals in the store):

```

```

## Proposal files

`tests/fixtures/sample_corpus/.corpuscle/proposals/` exists but contains no files, because the triage run did not reach the model.

```json
[]
```

## Agent run tool calls

None. No proposal was produced, so there is no `agent_run` to list.
