from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_probability_groups_propagate_exact_discrete_uncertainty():
    ledger = load_ledger(ROOT / "examples" / "fdcs_probability_policy.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    analysis = result.fdcs_projection["probability_analysis"]
    assert analysis["status"] == "PASS"
    a = analysis["groups"]["policy-a"]["transaction_uncertainty"]["outcome"]
    assert a["support_size"] == 2
    assert a["expected_value"] == pytest.approx(10.4)
    assert a["variance"] == pytest.approx(8.64)
    assert a["entropy_bits"] == pytest.approx(0.9709505944546686)
    assert a["minimum"] == 8.0
    assert a["maximum"] == 14.0


def test_policy_selection_uses_expected_utility_risk_and_cost():
    ledger = load_ledger(ROOT / "examples" / "fdcs_probability_policy.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    policy = result.fdcs_projection["policy_analysis"]
    assert policy["status"] == "PASS"
    assert policy["selected_policies"] == ["policy-a"]
    assert policy["policies"]["policy-a"]["score"] == pytest.approx(7.812122461732038)
    assert policy["policies"]["policy-b"]["score"] == pytest.approx(7.7)


def test_probability_mass_must_sum_to_one_within_each_policy():
    ledger = load_ledger(ROOT / "examples" / "fdcs_probability_policy.yaml")
    ledger.fdcs = deepcopy(ledger.fdcs)
    ledger.fdcs["contexts"][0]["probability"] = 0.5
    result = Runtime().execute(ledger, deterministic=True)
    group = result.fdcs_projection["probability_analysis"]["groups"]["policy-a"]
    assert group["status"] == "FAIL"
    assert group["probability_sum"] == pytest.approx(0.9)
    assert "expected 1.0" in group["errors"][0]


def test_positive_probability_on_conflicting_branch_is_rejected():
    ledger = load_ledger(ROOT / "examples" / "fdcs_observation_planning.yaml")
    ledger.fdcs = deepcopy(ledger.fdcs)
    ledger.fdcs["contexts"] = [
        {
            "id": "valid",
            "policy_id": "p",
            "probability": 0.5,
            "interventions": [
                {"id": "valid-set", "kind": "do_set", "target_tx_id": "root", "value": 4}
            ],
        },
        {
            "id": "conflict",
            "policy_id": "p",
            "probability": 0.5,
            "interventions": [
                {"id": "set-a", "kind": "do_set", "target_tx_id": "root", "value": 4},
                {"id": "set-b", "kind": "do_set", "target_tx_id": "root", "value": 5},
            ],
        },
    ]
    result = Runtime().execute(ledger, deterministic=True)
    group = result.fdcs_projection["probability_analysis"]["groups"]["p"]
    assert group["status"] == "FAIL"
    assert any("positive probability" in error for error in group["errors"])


def test_minimum_additional_observation_set_is_found_exactly():
    ledger = load_ledger(ROOT / "examples" / "fdcs_observation_planning.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    plan = result.fdcs_projection["observation_plan"]
    assert plan["status"] == "FOUND"
    assert plan["minimum_size"] == 1
    assert plan["solutions"] == [["root"]]
    assert plan["ambiguous_pairs"] == [["intervene-mid", "intervene-root"]]


def test_observation_planner_reports_structural_indistinguishability():
    ledger = load_ledger(ROOT / "examples" / "fdcs_observation_impossible.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    plan = result.fdcs_projection["observation_plan"]
    assert plan["status"] == "IMPOSSIBLE"
    assert plan["minimum_size"] is None
    assert plan["impossible_pairs"] == [["hard-root-four", "soft-root-plus-one"]]


def test_probability_policy_and_observation_hashes_are_deterministic():
    ledger = load_ledger(ROOT / "examples" / "fdcs_probability_policy.yaml")
    first = Runtime().execute(ledger, deterministic=True).fdcs_projection
    second = Runtime().execute(ledger, deterministic=True).fdcs_projection
    assert first["probability_analysis"]["analysis_hash"] == second["probability_analysis"]["analysis_hash"]
    assert first["policy_analysis"]["analysis_hash"] == second["policy_analysis"]["analysis_hash"]
