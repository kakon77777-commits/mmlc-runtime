from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from mmlc.errors import FDCSConfigurationError
from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_continuous_approximation_preserves_declared_moments_and_correlation():
    ledger = load_ledger(ROOT / "examples" / "fdcs_continuous_correlated.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    analysis = result.fdcs_projection["continuous_approximation_analysis"]
    ensemble = analysis["ensembles"]["correlated-shocks"]
    empirical = ensemble["empirical"]
    assert analysis["status"] == "PASS"
    assert empirical["means"]["a"] == pytest.approx(2.0, abs=1e-12)
    assert empirical["means"]["b"] == pytest.approx(-1.0, abs=1e-12)
    assert empirical["standard_deviations"]["a"] == pytest.approx(1.5, rel=0.03)
    assert empirical["standard_deviations"]["b"] == pytest.approx(0.5, rel=0.06)
    assert empirical["correlation_matrix"][0][1] == pytest.approx(0.65, abs=0.03)


def test_continuous_ensemble_becomes_auditable_probability_group():
    ledger = load_ledger(ROOT / "examples" / "fdcs_continuous_correlated.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    group = result.fdcs_projection["probability_analysis"]["groups"]["uncertainty-only"]
    assert group["status"] == "PASS"
    assert group["probability_sum"] == pytest.approx(1.0)
    assert len(group["contexts"]) == 256
    combined = group["transaction_uncertainty"]["combined"]
    assert combined["expected_value"] == pytest.approx(1.0, abs=1e-12)
    assert 240 <= combined["support_size"] <= 256
    assert sum(item["probability"] for item in combined["support"]) == pytest.approx(1.0)


def test_invalid_correlation_matrix_is_rejected():
    ledger = load_ledger(ROOT / "examples" / "fdcs_continuous_correlated.yaml")
    ledger.fdcs = deepcopy(ledger.fdcs)
    ledger.fdcs["continuous_uncertainty"]["ensembles"][0]["correlation_matrix"] = [
        [1.0, 1.2], [1.2, 1.0]
    ]
    with pytest.raises(FDCSConfigurationError):
        Runtime().execute(ledger, deterministic=True)


def test_observation_planner_reports_minimum_size_and_minimum_cost_separately():
    ledger = load_ledger(ROOT / "examples" / "fdcs_cost_aware_observation.yaml")
    plan = Runtime().execute(ledger, deterministic=True).fdcs_projection["observation_plan"]
    assert plan["status"] == "FOUND"
    assert plan["minimum_size"] == 1
    assert plan["solutions"] == [["z"]]
    assert plan["minimum_cost"] == pytest.approx(0.4)
    assert plan["minimum_cost_solutions"] == [["x", "y"]]


def test_information_value_computes_exact_one_step_evsi():
    ledger = load_ledger(ROOT / "examples" / "fdcs_sequential_information_value.yaml")
    analysis = Runtime().execute(ledger, deterministic=True).fdcs_projection["information_value_analysis"]
    assert analysis["status"] == "PASS"
    assert analysis["prior_best_value"] == pytest.approx(3.0)
    for candidate in ("signal_a", "signal_b"):
        row = analysis["candidate_information_values"][candidate]
        assert row["gross_information_value"] == pytest.approx(3.0)
        assert row["net_information_value"] == pytest.approx(2.5)


def test_finite_horizon_sequential_decision_uses_both_signals():
    ledger = load_ledger(ROOT / "examples" / "fdcs_sequential_information_value.yaml")
    analysis = Runtime().execute(ledger, deterministic=True).fdcs_projection["information_value_analysis"]
    assert analysis["horizon"] == 2
    assert analysis["sequential_expected_value"] == pytest.approx(11.0)
    assert analysis["sequential_net_information_value"] == pytest.approx(8.0)
    assert analysis["decision_tree"]["action"] == "observe"
    assert analysis["decision_tree"]["transaction"] == "signal_a"
    assert all(branch["next"]["action"] == "observe" for branch in analysis["decision_tree"]["branches"])


def test_high_observation_cost_makes_immediate_policy_choice_optimal():
    ledger = load_ledger(ROOT / "examples" / "fdcs_sequential_information_value.yaml")
    ledger.fdcs = deepcopy(ledger.fdcs)
    ledger.fdcs["information_value"]["observation_costs"] = {"signal_a": 20.0, "signal_b": 20.0}
    analysis = Runtime().execute(ledger, deterministic=True).fdcs_projection["information_value_analysis"]
    assert analysis["decision_tree"]["action"] == "choose_policy"
    assert analysis["sequential_expected_value"] == pytest.approx(analysis["prior_best_value"])
    assert analysis["sequential_net_information_value"] == pytest.approx(0.0)


def test_continuous_and_information_hashes_are_deterministic():
    continuous = load_ledger(ROOT / "examples" / "fdcs_continuous_correlated.yaml")
    first = Runtime().execute(continuous, deterministic=True).fdcs_projection
    second = Runtime().execute(continuous, deterministic=True).fdcs_projection
    assert first["continuous_approximation_analysis"]["analysis_hash"] == second["continuous_approximation_analysis"]["analysis_hash"]

    sequential = load_ledger(ROOT / "examples" / "fdcs_sequential_information_value.yaml")
    first_info = Runtime().execute(sequential, deterministic=True).fdcs_projection["information_value_analysis"]
    second_info = Runtime().execute(sequential, deterministic=True).fdcs_projection["information_value_analysis"]
    assert first_info["analysis_hash"] == second_info["analysis_hash"]
