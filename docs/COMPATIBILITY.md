# Compatibility policy

## Runtime semantic versioning

- Patch releases fix defects without intentionally changing the public API or MMLF semantics.
- Minor releases may add optional, backward-compatible API fields, commands, operators, or document fields.
- Major releases may remove or redefine stable behavior and must provide migration documentation.

## Supported documents

Runtime 1.0 loads MMLF 0.1 through 1.0.

Legacy documents execute according to their declared version. Documents migrated to 1.0 execute according to `metadata.migrated_from` when the migration profile is present.

## Stable public surface

The names exported from `mmlc.__init__` and listed by `mmlc info` are stable for Runtime 1.x.

Internal modules, private functions, experiment scripts, and generated report layout are not guaranteed to remain byte-for-byte unchanged.

## Hash compatibility

Semantic hashes are reproducible within the same runtime/operator lock and deterministic mode. A runtime upgrade may intentionally change a hash when a defect in semantics, canonicalization, or audit output is fixed. Compatibility should therefore be checked using manifests, runtime versions, operator locks, and migration snapshots—not a hash alone.
