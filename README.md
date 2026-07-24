# MMLC Runtime

**Multidirectional Matrix Ledger Computation Runtime**

MMLC Runtime is an auditable Python runtime for typed matrix-ledger documents. It combines deterministic arithmetic and symbolic execution, dependency and provenance tracking, multidirectional matrix traversal, cross-axis constraints, temporal dynamics, counterfactual branches, uncertainty propagation, and finite decision analysis in one inspectable execution model.

> Version 1.0 stabilizes the public API, CLI, MMLF document profile, migration path, packaged schemas, release benchmarks, and repository structure. It does not claim that MMLC replaces spreadsheets, DAG engines, symbolic systems, causal-inference libraries, numerical solvers, or probabilistic programming tools.

[繁體中文說明](README.zh-TW.md)

## Status

- Runtime: `1.0.0`
- Stable document profile: MMLF `1.0`
- Backward-compatible loaders: MMLF `0.1` through `0.9`
- Python: `3.10+`
- License: Apache-2.0
- Test suite: 71 tests before release validation
- Historical experiments: E0–E9

## Repository name

```text
mmlc-runtime
```

Suggested GitHub description:

> Auditable multidirectional matrix-ledger runtime for deterministic computation, constraints, temporal dynamics, counterfactuals, uncertainty, and finite decision analysis.

Suggested topics:

```text
matrix-computation ledger audit counterfactual causal-inference
symbolic-computation uncertainty decision-analysis python
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## Quick start

```bash
mmlc validate examples/mmlf_v1_stable.yaml
mmlc run examples/mmlf_v1_stable.yaml \
  --output outputs/quickstart \
  --deterministic \
  --fail-on-audit
```

Python API:

```python
from mmlc import execute_file, validate_file

summary = validate_file("examples/mmlf_v1_stable.yaml")
result = execute_file("examples/mmlf_v1_stable.yaml", deterministic=True)

assert summary.version == "1.0"
assert result.global_audit["status"] == "PASS"
```

## Migration to MMLF 1.0

```bash
mmlc migrate examples/four_operations.yaml \
  --output migrated/four_operations_v1.yaml
```

The migrator:

1. validates the source document using its original schema;
2. canonicalizes legacy syntax;
3. writes a stable MMLF 1.0 document;
4. preserves the original semantic feature profile through metadata;
5. validates the migrated document;
6. executes source and target deterministically and compares a version-independent snapshot.

## Stable commands

```text
mmlc info
mmlc validate
mmlc migrate
mmlc run
mmlc verify-exchange
mmlc compare-directions
mmlc compare-representations
mmlc simulate-fdcs
mmlc benchmark
```

## Main capability layers

```text
Typed transactions and operator invariants
→ local, regional and global audit
→ dependency taint and root-cause paths
→ matrix layout and multidirectional traversal
→ row, column and block constraints
→ minimum-support repair proposals
→ temporal references and fixed-point groups
→ append-only corrections
→ hard and soft counterfactual interventions
→ branch differential ledgers
→ discrete and deterministic continuous uncertainty
→ policy scoring, information value and finite sequential decisions
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Stable Python API](docs/API.md)
- [CLI reference](docs/CLI.md)
- [MMLF 1.0 profile](docs/MMLF_1.0.md)
- [Migration guide](docs/MIGRATION.md)
- [Compatibility policy](docs/COMPATIBILITY.md)
- [Limitations and non-claims](docs/LIMITATIONS.md)
- [GitHub setup and release](docs/GITHUB_SETUP.md)
- [Post-1.0 roadmap](docs/ROADMAP.md)
- [v1.0 stabilization report](MMLC_Runtime_v1.0_穩定化與發布驗證報告.md)
- [Benchmarks](benchmarks/README.md)
- [Release notes](RELEASE_NOTES_v1.0.0.md)

## Reproducibility

```bash
python -m pytest -q
python experiments/release_v1/run_release_v1.py
python benchmarks/run_release_benchmark.py
```

Generated runs contain canonical JSON, semantic and execution hashes, event logs, manifests, and Markdown reports.

## Citation

Citation metadata is provided in [`CITATION.cff`](CITATION.cff).

## Project scope

MMLC is currently a deterministic research runtime and executable specification. Declared probabilities, causal structures, costs, utilities, and observation models are model inputs. They are not automatically inferred truths about the external world.
