# MMLF 1.0 stable profile

MMLF is the Matrix Ledger Format consumed by MMLC Runtime.

## Stability rule

MMLF 1.0 freezes the document surface and computational semantics implemented by Runtime 0.9. Runtime 1.x may add optional backward-compatible fields, but an incompatible semantic change requires MMLF 2.0 and a migration path.

## Required root fields

```yaml
format: MMLF
version: "1.0"
ledger_id: example
branches: []
```

At least one branch is required by the schema.

## Optional root sections

- `metadata`
- `objects`
- `layout`
- `traversals`
- `audit_policy`
- `evaluation_scenarios`
- `constraints`
- `fixed_point_groups`
- `corrections`
- `fdcs`
- `boundary_events`

## Metadata

```yaml
metadata:
  title: Example
  description: Stable MMLF 1.0 document
  authors: [Neo.K]
  license: Apache-2.0
```

Migrated documents additionally contain:

```yaml
metadata:
  migrated_from: "0.5"
  migrated_by: "mmlc-runtime 1.0.0"
  migration_profile: mmlf-stable-1.0
```

`migrated_from` is operational. It preserves the source document's historical feature profile so that migration does not silently activate later execution semantics.

## Schemas

All schemas are distributed inside the Python package under `mmlc.schemas`, so validation works from editable installs, wheels, source distributions, and normal installed environments.

## Canonical values

MMLC preserves exact fractions and symbolic values where supported. Output serialization uses canonical tagged representations rather than silently converting every value to floating point.

## Schema versus semantics

JSON Schema validates document shape. Runtime validation additionally checks IDs, layouts, references, operator domains, dependency cycles, intervention conflicts, fixed-point contracts, and feature-specific invariants.
