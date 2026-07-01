# Contributing

Thanks for contributing to `CnEquityStrategies`.

## Ground Rules

- Prefer small pull requests with one clear purpose.
- Keep refactors separate from behavior, contract, workflow, or documentation changes.
- Preserve this repository's boundary as an A-share equity strategy package; do not move broker execution, live-allocation decisions, private credentials, or unrelated platform logic into it.
- Add or update tests, examples, docs, or reproducible evidence when changing behavior or public contracts.

## Local Verification

```bash
python -m pip install -e '.[test]'
python -m pip check
ruff check .
PYTHONPATH=src python -m pytest -q tests
python scripts/smoke_cn_index_etf_tactical_rotation_dry_run.py --json
python -m build
```

## Branching and Pull Requests

- Create a topic branch for each change.
- Open a pull request with a concise summary, scope boundary, and concrete validation notes.
