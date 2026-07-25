# CLI reference

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | command completed |
| 2 | usage, validation, migration, or explicit configuration error |
| 3 | audit/comparison failure when the command requests failure propagation |
| 4 | unexpected internal error |

## Commands

### `mmlc info`

Print runtime, API, schema, command, and compatibility information.

### `mmlc validate LEDGER`

Validate and construct an MMLF document.

### `mmlc migrate LEDGER --output FILE`

Migrate MMLF v0.1–v0.9 to MMLF 1.0. Execution-equivalence verification is enabled by default.

Use `--no-execution-verify` only when migration of an intentionally expensive document must be separated from later verification.

### `mmlc run LEDGER --output DIR`

Execute and audit a ledger.

Options:

- `--deterministic`
- `--execution-traversal NAME`
- `--fail-on-audit`

### `mmlc simulate-fdcs LEDGER --output DIR`

Execute FDCS projections, branches, uncertainty, policy, information-value, and observation-planning analyses declared by the document.

### `mmlc verify-exchange LEDGER --output DIR`

Verify symbolic–numeric execution/substitution commutation for declared scenarios.

### `mmlc compare-directions LEDGER --output DIR`

Execute a ledger under multiple physical traversal directions.

### `mmlc compare-representations LEDGER --output DIR`

Compare matrix constraints against the independent flat-table reference implementation and export the factor graph.

### `mmlc benchmark`

Run the small release benchmark suite.

```bash
mmlc benchmark \
  --sizes 64 256 1024 \
  --repeats 3 \
  --output release/benchmark_v1.0.json
```
