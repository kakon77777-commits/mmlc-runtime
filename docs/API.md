# Stable Python API — Runtime 1.x

The following imports are stable for the Runtime 1.x series:

```python
from mmlc import (
    Runtime,
    load_ledger,
    validate_file,
    execute_file,
    simulate_fdcs_file,
    migrate_file,
    runtime_info,
    save_result,
    verify_symbolic_numeric_exchange,
    compare_directions,
    compare_representations,
)
```

## Validation

```python
summary = validate_file("ledger.yaml")
```

Returns `ValidationSummary` with the ledger ID, document version, transaction count, matrix shape, and FDCS status.

## Execution

```python
result = execute_file(
    "ledger.yaml",
    deterministic=True,
    execution_traversal=None,
)
```

Returns `RunResult`. Stable top-level result fields for Runtime 1.x include:

- `ledger_id`
- `runtime_version`
- `execution_order`
- `execution_traversal`
- `transactions`
- `global_audit`
- `root_cause_analysis`
- `constraint_audits`
- `repair_analysis`
- `temporal_analysis`
- `fixed_point_analysis`
- `correction_analysis`
- `fdcs_projection`
- `semantic_hash`
- `execution_hash`
- `manifest`

New fields may be added in minor versions. Existing stable fields will not be removed or redefined before Runtime 2.0.

## Migration

```python
report = migrate_file(
    "legacy.yaml",
    "stable.yaml",
    target_version="1.0",
    verify_execution=True,
)
```

The migration report records source and target versions, validation status, source and target outcomes, version-independent execution snapshot hashes, and a deterministic migration hash.

## Persistence

```python
save_result(result, "outputs/run", deterministic=True)
```

Writes canonical JSON, Markdown, events, and a manifest. FDCS runs also receive an FDCS report.

## Low-level API

`Runtime`, `load_ledger`, and the comparison functions remain public for advanced use. Modules not exported from `mmlc.__init__` are internal and may change in Runtime 1.x when necessary to fix implementation defects.
