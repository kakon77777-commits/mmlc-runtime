from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmlc import execute_file, runtime_info, validate_file  # noqa: E402
from mmlc.benchmark import run_release_benchmarks  # noqa: E402
from mmlc.migration import migrate_file  # noqa: E402
from mmlc.persistence import semantic_hash  # noqa: E402
from mmlc.version import __version__  # noqa: E402


def main() -> None:
    release_dir = ROOT / "release"
    migrated_dir = release_dir / "migrated_examples"
    if migrated_dir.exists():
        shutil.rmtree(migrated_dir)
    migrated_dir.mkdir(parents=True, exist_ok=True)

    examples = sorted(
        path for path in (ROOT / "examples").iterdir()
        if path.suffix.lower() in {".yaml", ".yml", ".json"}
    )
    migrations = []
    for source in examples:
        target = migrated_dir / source.name
        report = migrate_file(source, target, verify_execution=False)
        validate_file(target)
        migrations.append({
            "file": source.name,
            "source_version": report.source_version,
            "target_version": report.target_version,
            "migration_hash": report.migration_hash,
        })

    representatives = [
        "four_operations.yaml",
        "symbolic_exchange.yaml",
        "directional_previous_scan.yaml",
        "cross_axis_single_error.yaml",
        "temporal_lag_chain.yaml",
        "fdcs_intervention_branches.yaml",
        "fdcs_soft_interventions.yaml",
        "fdcs_probability_policy.yaml",
        "fdcs_continuous_correlated.yaml",
        "division_by_zero.yaml",
        "dependency_cycle.yaml",
        "fixed_point_divergent.yaml",
    ]
    equivalence = []
    for name in representatives:
        source = ROOT / "examples" / name
        target = migrated_dir / name
        report = migrate_file(source, target, verify_execution=True)
        equivalence.append({
            "file": name,
            "source_outcome": report.source_outcome,
            "target_outcome": report.target_outcome,
            "equivalent": report.execution_equivalent,
            "source_snapshot_hash": report.source_snapshot_hash,
            "target_snapshot_hash": report.target_snapshot_hash,
        })

    native_summary = validate_file(ROOT / "examples" / "mmlf_v1_stable.yaml")
    native_result = execute_file(ROOT / "examples" / "mmlf_v1_stable.yaml", deterministic=True)
    benchmark = run_release_benchmarks(sizes=(64, 256, 1024), repeats=3)
    benchmark_path = release_dir / "benchmark_v1.0.json"
    benchmark_path.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    metrics = {
        "release_validation_format": "MMLC-RELEASE-VALIDATION v1",
        "runtime_version": __version__,
        "runtime_info": runtime_info(),
        "example_count": len(examples),
        "migrated_example_count": len(migrations),
        "migration_validation_failures": 0,
        "representative_equivalence_count": len(equivalence),
        "representative_equivalence_failures": sum(not item["equivalent"] for item in equivalence),
        "migrations": migrations,
        "representative_equivalence": equivalence,
        "native_v1": {
            "ledger_id": native_summary.ledger_id,
            "version": native_summary.version,
            "transaction_count": native_summary.transaction_count,
            "global_status": native_result.global_audit["status"],
            "semantic_hash": native_result.semantic_hash,
        },
        "packaged_schema_count": len(list((ROOT / "mmlc" / "schemas").glob("*.schema.json"))),
        "root_schema_count": len(list((ROOT / "schemas").glob("*.schema.json"))),
        "benchmark_hash": benchmark["benchmark_hash"],
        "benchmark_cases": len(benchmark["cases"]),
        "all_benchmark_hashes_identical": all(item["hashes_identical"] for item in benchmark["cases"]),
        "all_benchmark_audits_pass": all(item["global_status"] == "PASS" for item in benchmark["cases"]),
    }
    metrics["release_hash"] = semantic_hash(metrics)
    output = release_dir / "release_validation_v1.0.json"
    output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
