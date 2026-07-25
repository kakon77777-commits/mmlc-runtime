# Contributing

Thank you for considering a contribution to MMLC Runtime.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

## Contribution rules

- Add or update tests for every semantic change.
- Preserve deterministic output when `deterministic=True`.
- Do not silently relax audit failures.
- Distinguish model assumptions from externally verified facts.
- Update MMLF schemas, migration logic, documentation, and compatibility notes together.
- Incompatible public API or document-semantic changes require a major version proposal.

## Pull requests

Include:

- the problem being solved;
- the affected API or MMLF fields;
- tests and reproduction steps;
- compatibility impact;
- benchmark evidence when performance is claimed;
- explicit limitations and non-claims.
