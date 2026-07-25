from pathlib import Path

import pytest

from mmlc.errors import DependencyCycleError
from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_temporal_lag_chain_and_fdcs_projection():
    ledger = load_ledger(ROOT / "examples" / "temporal_lag_chain.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    assert result.global_audit["status"] == "PASS"
    assert result.execution_order == ["x-t0", "x-t1", "x-t2", "y-t2"]
    assert result.transactions["x-t2"].computed_result == 5
    assert result.transactions["y-t2"].computed_result == 10
    assert len(result.temporal_analysis["delayed_edges"]) == 3
    assert result.temporal_analysis["causal_time_order_valid"] is True
    assert result.fdcs_projection["status"] == "PROJECTED"
    temporal_edges = [e for e in result.fdcs_projection["edges"] if e["lag"] > 0]
    assert temporal_edges
    for edge in temporal_edges:
        assert edge["effective_weight"] == pytest.approx(0.8 ** edge["lag"])
    assert result.fdcs_projection["interventions"][0]["status"] == "DECLARED_NOT_EXECUTED"


def test_temporal_default_at_series_boundary():
    ledger = load_ledger(ROOT / "examples" / "temporal_default.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    assert result.global_audit["status"] == "PASS"
    assert result.transactions["x-t0"].computed_result == 5


def test_declared_fixed_point_converges():
    ledger = load_ledger(ROOT / "examples" / "fixed_point_convergent.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    group = result.fixed_point_analysis["groups"]["xy-equilibrium"]
    assert group["converged"] is True
    assert group["iterations"] < 200
    assert result.global_audit["status"] == "PASS"
    assert float(result.transactions["x"].computed_result) == pytest.approx(2.0, abs=1e-10)
    assert float(result.transactions["y"].computed_result) == pytest.approx(2.0, abs=1e-10)


def test_declared_fixed_point_nonconvergence_is_explicit():
    ledger = load_ledger(ROOT / "examples" / "fixed_point_divergent.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    group = result.fixed_point_analysis["groups"]["xy-divergent"]
    assert group["converged"] is False
    assert result.global_audit["status"] == "FAIL"
    assert result.transactions["x"].status == "ERROR"
    assert result.transactions["y"].error_type == "FixedPointConvergenceError"


def test_undeclared_cycle_still_rejected():
    ledger = load_ledger(ROOT / "examples" / "dependency_cycle.yaml")
    with pytest.raises(DependencyCycleError):
        Runtime().execute(ledger, deterministic=True)


def test_append_only_corrections_preserve_original_and_build_hash_chain():
    ledger = load_ledger(ROOT / "examples" / "immutable_correction.yaml")
    original = ledger.transactions["multiply-claim"].declared_result
    result = Runtime().execute(ledger, deterministic=True)
    tx = result.transactions["multiply-claim"]
    assert original == 7
    assert ledger.transactions["multiply-claim"].declared_result == 7
    assert tx.original_declared_result == 7
    assert tx.effective_declared_result == 6
    assert tx.corrections_applied == ["correction-001", "correction-002"]
    assert tx.status == "PASS"
    entries = result.correction_analysis["entries"]
    assert len(entries) == 2
    assert entries[1].previous_hash == entries[0].entry_hash
    assert result.correction_analysis["head_hash"] == entries[-1].entry_hash
    again = Runtime().execute(ledger, deterministic=True)
    assert again.correction_analysis["head_hash"] == result.correction_analysis["head_hash"]
