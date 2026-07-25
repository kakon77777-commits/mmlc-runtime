# Migration guide

## Command

```bash
mmlc migrate old.yaml --output new.yaml
```

## Guarantees

The v1.0 migrator performs six steps:

1. validate the source with its original MMLF schema;
2. deep-copy the source document;
3. canonicalize supported legacy shorthand;
4. set `version: "1.0"` and write migration metadata;
5. validate and parse the target document;
6. compare deterministic, version-independent execution snapshots.

A mismatch raises an explicit migration error and leaves evidence in the command output.

## Preserving old semantics

A migrated MMLF 0.5 document remains on the 0.5 feature profile even though its new document syntax is 1.0. This matters for historically declaration-only interventions and other capabilities introduced in later versions.

Native MMLF 1.0 documents use the full stable 1.0 feature profile.

## Legacy intervention shorthand

The migrator converts:

```yaml
- target: x
  value: 10
```

into:

```yaml
- id: migrated-intervention-1
  kind: do_set
  target_tx_id: x
  value: 10
```

The conversion normalizes syntax only. Whether the intervention executes is determined by the preserved semantic profile.

## Batch migration

The release validation script migrates all repository examples and performs representative execution-equivalence checks:

```bash
python experiments/release_v1/run_release_v1.py
```
