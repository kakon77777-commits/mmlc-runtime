# MMLC Runtime v1.0.0

MMLC Runtime 1.0 is the first stable release of the Multidirectional Matrix Ledger Computation runtime.

## Stable release changes

- freezes the Runtime 1.x public Python API;
- freezes the MMLF 1.0 document profile;
- retains loaders for MMLF 0.1–0.9;
- adds deterministic legacy-to-1.0 migration with execution-equivalence verification;
- preserves historical feature semantics through `metadata.migrated_from`;
- packages all schemas inside the installed Python distribution;
- adds machine-readable CLI errors and documented exit codes;
- adds `mmlc info`, `mmlc migrate`, and `mmlc benchmark`;
- adds GitHub Actions CI, issue templates, security and contribution documentation;
- adds release benchmarks, compatibility documentation, and a release-verification experiment;
- corrects rejection of unknown future MMLF versions instead of silently treating them as v0.1.

## Computational scope

Runtime 1.0 includes the E0–E9 capabilities developed during the pre-1.0 series: deterministic matrix-ledger execution and audit, symbolic exchange, provenance and root causes, multidirectional layout, cross-axis constraints and repair, temporal and fixed-point execution, append-only corrections, hard and soft counterfactuals, uncertainty propagation, policy analysis, information value, and finite sequential decisions.

No new mathematical capability was added solely to reach 1.0. The release is a stabilization and publication boundary.

## Compatibility

MMLF v0.1–v0.9 documents remain loadable. Migration to v1.0 is recommended before long-term publication or interchange.

## License

Apache License 2.0.
