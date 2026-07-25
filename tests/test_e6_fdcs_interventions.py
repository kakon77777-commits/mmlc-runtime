from __future__ import annotations

from pathlib import Path

import pytest

from mmlc.errors import InterventionError
from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_virtual_intervention_cuts_incoming_edge_and_recomputes_descendants():
    ledger = load_ledger(ROOT / "examples" / "fdcs_intervention_branches.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    assert result.global_audit["status"] == "PASS"
    assert result.fdcs_projection["status"] == "EXECUTED"
    contexts = result.fdcs_projection["contexts"]
    assert contexts["observed"]["values"] == {"leaf": 10, "mid": 6, "root": 3, "seed": 2}
    root_branch = contexts["do-root-10"]
    assert root_branch["values"] == {"leaf": 24, "mid": 20, "root": 10, "seed": 2}
    assert root_branch["changed_transactions"] == ["leaf", "mid", "root"]
    assert root_branch["cut_edges"] == [{
        "source": "seed",
        "target": "root",
        "channels": ["base:result"],
        "intervention_id": "set-root-10",
    }]
    assert root_branch["global_audit"] == "PASS"
    assert root_branch["counterfactual_declared_results_ignored"] is True


def test_middle_intervention_changes_only_target_and_descendants():
    ledger = load_ledger(ROOT / "examples" / "fdcs_intervention_branches.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    branch = result.fdcs_projection["contexts"]["do-mid-1"]
    assert branch["values"] == {"leaf": 5, "mid": 1, "root": 3, "seed": 2}
    assert branch["changed_transactions"] == ["leaf", "mid"]
    assert branch["cut_edges"][0]["source"] == "root"
    assert branch["cut_edges"][0]["target"] == "mid"


def test_multicontext_branches_execute_independently_and_in_parallel_mode():
    ledger = load_ledger(ROOT / "examples" / "fdcs_intervention_branches.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    fdcs = result.fdcs_projection
    assert fdcs["execution_mode"] == "parallel_thread_pool"
    assert fdcs["parallel_workers"] == 3
    assert fdcs["branch_order"] == ["observed", "do-mid-1", "do-root-10", "high-weight"]
    assert fdcs["all_contexts_executed"] is True
    assert fdcs["contexts"]["high-weight"]["changed_transactions"] == []
    assert fdcs["contexts"]["high-weight"]["projection"]["context_modulation"] == 2.0


def test_directional_and_fractal_weight_formula():
    ledger = load_ledger(ROOT / "examples" / "fdcs_directional_fractal_weights.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    edge = result.fdcs_projection["edges"][0]
    # 2 * 0.5^2 * 0.8^2 * 1.2 * 1.5 = 0.576
    assert edge["forward_effective_weight"] == pytest.approx(0.576)
    # 2 * 0.5^2 * 0.8^2 * 1.2 * 0.25 = 0.096
    assert edge["reverse_effective_weight"] == pytest.approx(0.096)
    assert edge["fractal_level_gap"] == 2
    amplified = result.fdcs_projection["contexts"]["amplified"]["projection"]["edges"][0]
    assert amplified["forward_effective_weight"] == pytest.approx(0.96)
    assert amplified["reverse_effective_weight"] == pytest.approx(0.16)


def test_invalid_intervention_target_is_explicit_error():
    ledger = load_ledger(ROOT / "examples" / "fdcs_invalid_intervention.yaml")
    with pytest.raises(InterventionError):
        Runtime().execute(ledger, deterministic=True)


def test_fdcs_context_hashes_are_deterministic():
    ledger = load_ledger(ROOT / "examples" / "fdcs_intervention_branches.yaml")
    first = Runtime().execute(ledger, deterministic=True)
    second = Runtime().execute(ledger, deterministic=True)
    assert first.semantic_hash == second.semantic_hash
    for context_id in first.fdcs_projection["contexts"]:
        assert first.fdcs_projection["contexts"][context_id]["semantic_hash"] == second.fdcs_projection["contexts"][context_id]["semantic_hash"]


def test_intervention_inside_fixed_point_group_is_rejected():
    ledger = load_ledger(ROOT / "examples" / "fixed_point_convergent.yaml")
    ledger.version = "0.6"
    ledger.fdcs = {
        "enabled": True,
        "base_context": "observed",
        "contexts": [{
            "id": "illegal-fixed-point-cut",
            "interventions": [{
                "id": "set-x",
                "kind": "do_set",
                "target_tx_id": "x",
                "value": 1,
            }],
        }],
    }
    with pytest.raises(InterventionError):
        Runtime().execute(ledger, deterministic=True)
