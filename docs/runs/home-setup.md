# Local setup on the home machine

Date: 2026-10-06

- OS: Windows 10 Education 10.0.19045
- Python: 3.11.4
- Clone path: `C:\corpuscle` (fresh `git clone` of `main` at `10f7954`)

Commands were run from the repository root in a fresh virtualenv. `py -m venv .venv` picks Python 3.9.6 on this machine, which is below the project's `requires-python = ">=3.10"` and makes the editable install fail, so the virtualenv was created with the 3.11 interpreter instead:

```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,agents]"
```

The install resolved `anthropic` 1.11.0, `cryptography` 50.0.2, `datasketch` 1.10.0 and `pytest` 9.1.1.

`corpuscle triage` was not run. No environment variable values were printed or stored. `keys/`, `.venv/` and `tests/fixtures/sample_corpus/.corpuscle/` were left out of git.

## Tests

`pytest -q` summary line:

```
48 passed in 9.58s
```

## Keygen

```
$ corpuscle keygen --out keys
wrote keys/dev.key.pem and keys/dev.pub.pem
```

## Scan

```
$ corpuscle scan tests/fixtures/sample_corpus --corpus-id sample --version-id v1 --key keys/dev.key.pem
bundle written to tests\fixtures\sample_corpus/.corpuscle  root=17c172006b760dc5…  docs=14
policy corpuscle-default/0.1.0
  FAIL         medium   DUP-001  duplication.exact    0.142857 fraction > 0.1
  FAIL         high     DUP-002  duplication.near     0.285714 fraction > 0.1
```

Exit code 0. The two FAIL lines are policy findings on the sample corpus, not errors of the run.

## Verify

```
$ corpuscle verify tests/fixtures/sample_corpus --pub keys/dev.pub.pem
PASS  signature
PASS  manifest schema
PASS  records hash
PASS  records count
PASS  merkle root
PASS  statement subject
PASS  corpus files match records
RESULT  verified
```

Exit code 0.
