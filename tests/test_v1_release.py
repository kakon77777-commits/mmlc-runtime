from __future__ import annotations

from pathlib import Path

import pytest

from mmlc import execute_file, runtime_info, validate_file
from mmlc.benchmark import run_release_benchmarks
from mmlc.cli import main
from mmlc.errors import SchemaValidationError
from mmlc.migration import migrate_file
from mmlc.parser import load_ledger, schema_text
from mmlc.semantics import semantic_profile

ROOT = Path(__file__).resolve().parent.parent


def test_stable_public_api_and_native_v1_document():
    info = runtime_info()
    assert info["version"] == "1.0.0"
    assert info["mmlf_stable_version"] == "1.0"
    summary = validate_file(ROOT / "examples" / "mmlf_v1_stable.yaml")
    assert summary.version == "1.0"
    assert summary.transaction_count == 2
    result = execute_file(ROOT / "examples" / "mmlf_v1_stable.yaml")
    assert result.global_audit["status"] == "PASS"
    assert result.runtime_version == "1.0.0"


def test_all_schemas_are_package_resources():
    for version in ["0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1.0"]:
        text = schema_text(version)
        assert '"$schema"' in text


def test_unknown_schema_version_is_rejected(tmp_path: Path):
    path = tmp_path / "future.yaml"
    path.write_text(
        "format: MMLF\nversion: '2.0'\nledger_id: future\nbranches:\n  - {id: x, operator: identity, base: 1}\n",
        encoding="utf-8",
    )
    with pytest.raises(SchemaValidationError):
        load_ledger(path)


def test_migration_preserves_execution_for_v01(tmp_path: Path):
    output = tmp_path / "four_operations_v1.yaml"
    report = migrate_file(ROOT / "examples" / "four_operations.yaml", output)
    assert report.target_version == "1.0"
    assert report.execution_equivalent is True
    migrated = load_ledger(output)
    assert migrated.version == "1.0"
    assert semantic_profile(migrated) == "0.1"


def test_migration_preserves_pre_v06_declared_only_intervention_semantics(tmp_path: Path):
    output = tmp_path / "temporal_v1.yaml"
    report = migrate_file(ROOT / "examples" / "temporal_lag_chain.yaml", output)
    assert report.execution_equivalent is True
    migrated = load_ledger(output)
    assert semantic_profile(migrated) == "0.5"
    result = execute_file(output)
    projection = result.fdcs_projection["contexts"]["temporal-test"]["projection"]
    assert projection["interventions"][0]["status"] == "DECLARED_NOT_EXECUTED"
    assert projection["cut_edges"] == []


def test_release_benchmark_smoke():
    result = run_release_benchmarks(sizes=[8], repeats=2)
    assert len(result["cases"]) == 2
    assert all(case["hashes_identical"] for case in result["cases"])
    assert all(case["global_status"] == "PASS" for case in result["cases"])


def test_cli_info_and_migrate(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert main(["info"]) == 0
    assert '"version": "1.0.0"' in capsys.readouterr().out
    output = tmp_path / "migrated.yaml"
    assert main([
        "migrate",
        str(ROOT / "examples" / "four_operations.yaml"),
        "--output",
        str(output),
    ]) == 0
    assert output.exists()
