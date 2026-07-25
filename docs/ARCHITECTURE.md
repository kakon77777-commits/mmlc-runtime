# Architecture

```text
MMLF YAML/JSON
  ↓ schema and structural validation
Typed MatrixLedger IR
  ↓ layout, temporal and dependency resolution
Operator Registry
  ↓ deterministic execution / fixed-point units
Local Audit
  ↓ source, domain, value and dependency checks
Matrix Audit
  ↓ row, column, block and region constraints
Provenance Analysis
  ↓ taint, roots and paths
Repair Analysis
  ↓ minimum-support proposals
FDCS Layer
  ↓ counterfactual contexts, uncertainty and decisions
Persistence
  ↓ canonical JSON, hashes, events, manifests and reports
```

## Separation of concerns

- Layout is not transaction identity.
- Display traversal is not necessarily execution traversal.
- A locally correct computation can consume an untrusted declared channel.
- A repair proposal is not automatically the unique real-world root cause.
- A reverse query weight is not reverse causation.
- A declared branch probability is not learned objective probability.
- Deterministic continuous sampling is a finite approximation, not analytic inference.

## Package layout

- `mmlc/`: runtime implementation and stable API
- `mmlc/schemas/`: installed schema resources
- `schemas/`: human-readable schema copies
- `examples/`: documents covering MMLF capabilities
- `tests/`: unit and regression suite
- `experiments/`: E0–E9 and release validation
- `benchmarks/`: reproducible implementation benchmarks
- `docs/`: stable public documentation
- `release/`: generated release evidence
