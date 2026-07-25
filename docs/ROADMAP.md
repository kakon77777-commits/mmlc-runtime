# Roadmap after 1.0

Runtime 1.0 is a stabilization boundary. New work should prefer depth over feature accumulation.

## 1.0.x

- correctness and security fixes;
- documentation corrections;
- deterministic-output defects;
- packaging and installation fixes;
- benchmark methodology corrections.

## 1.1 candidates

- typed extension/plugin contract without arbitrary document code execution;
- streaming input and bounded-memory event persistence;
- improved sparse constraint repair backends;
- optional formal operator specifications;
- cross-runtime conformance fixtures;
- profile-guided performance work based on public benchmarks.

## Separate repositories when mature

- `mmlc-spec`: normative MMLF and semantic specification;
- `mmlc-bench`: comparative and adversarial benchmark suite;
- `mmlc-docs`: public documentation site;
- language bindings or visual editors.

Major semantic expansion should not be placed into Runtime 1.x merely to continue version-number growth.
