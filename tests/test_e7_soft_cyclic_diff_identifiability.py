from __future__ import annotations

from pathlib import Path

import pytest

from mmlc.fdcs import audit_intervention_set
from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_soft_affine_preserves_incoming_edges_and_changes_descendants():
    ledger = load_ledger(ROOT / "examples" / "fdcs_soft_interventions.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    branch = result.fdcs_projection["contexts"]["soften-root"]
    assert branch["values"] == {"leaf": 18, "mid": 14, "root": 7, "seed": 2}
    assert branch["cut_edges"] == []
    root = branch["projection"]["nodes"][2]
    assert root["node_id"] == "root"
    assert root["structural_state"] == 3
    assert root["state"] == 7
    assert root["intervention_kinds"] == ["soft_affine"]
    edges = {(edge["source"], edge["target"]) for edge in branch["projection"]["edges"]}
    assert ("seed", "root") in edges


def test_hard_intervention_inside_fixed_point_group_re_solves_cycle():
    ledger = load_ledger(ROOT / "examples" / "fdcs_fixed_point_interventions.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    branch = result.fdcs_projection["contexts"]["hard-x-four"]
    assert branch["values"]["x"] == 4
    assert branch["values"]["y"] == pytest.approx(3.0)
    assert branch["cut_edges"] == [{
        "source": "y",
        "target": "x",
        "channels": ["base:result"],
        "intervention_id": "set-x-four",
    }]
    group = branch["projection"]
    assert group["nodes"][0]["intervention_kinds"] == ["do_set"]
    assert branch["global_audit"] == "PASS"


def test_soft_intervention_inside_fixed_point_group_re_solves_transformed_equation():
    ledger = load_ledger(ROOT / "examples" / "fdcs_fixed_point_interventions.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    branch = result.fdcs_projection["contexts"]["soft-x-shift"]
    assert branch["cut_edges"] == []
    assert branch["values"]["x"] == pytest.approx(10 / 3, rel=1e-10)
    assert branch["values"]["y"] == pytest.approx(8 / 3, rel=1e-10)
    x_record = next(record for record in branch["differential_ledger"]["records"] if record["tx_id"] == "x")
    y_record = next(record for record in branch["differential_ledger"]["records"] if record["tx_id"] == "y")
    assert x_record["change_role"] == "soft_intervention"
    assert y_record["change_role"] == "fixed_point_response"


def test_branch_differential_ledger_is_hash_chained_and_deterministic():
    ledger = load_ledger(ROOT / "examples" / "fdcs_soft_interventions.yaml")
    first = Runtime().execute(ledger, deterministic=True)
    second = Runtime().execute(ledger, deterministic=True)
    left = first.fdcs_projection["contexts"]["shift-mid"]["differential_ledger"]
    right = second.fdcs_projection["contexts"]["shift-mid"]["differential_ledger"]
    assert left["head_hash"] == right["head_hash"]
    assert left["changed_count"] == 2
    previous = "0" * 64
    for record in left["records"]:
        assert record["previous_hash"] == previous
        previous = record["entry_hash"]
    assert previous == left["head_hash"]


def test_conflicting_context_is_isolated_while_valid_contexts_execute():
    ledger = load_ledger(ROOT / "examples" / "fdcs_conflict_identifiability.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    fdcs = result.fdcs_projection
    assert fdcs["status"] == "PARTIAL"
    assert fdcs["all_contexts_executed"] is False
    assert fdcs["contexts"]["conflicting-root"]["status"] == "CONFLICT"
    assert fdcs["contexts"]["hard-root-four"]["status"] == "EXECUTED"
    assert fdcs["contexts"]["soft-root-plus-one"]["status"] == "EXECUTED"
    conflict = fdcs["contexts"]["conflicting-root"]["intervention_audit"]["conflicts"][0]
    assert conflict["target_tx_id"] == "root"


def test_identifiability_audit_preserves_observational_equivalence_classes():
    ledger = load_ledger(ROOT / "examples" / "fdcs_conflict_identifiability.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    audit = result.fdcs_projection["identifiability_audit"]
    assert audit["observed_transactions"] == ["leaf"]
    assert ["hard-root-four", "soft-root-plus-one"] in audit["equivalence_classes"]
    assert ["invisible-identity", "observed"] in audit["equivalence_classes"]
    assert audit["context_results"]["hard-root-four"]["status"] == "EFFECT_VISIBLE_CONTEXT_NOT_UNIQUE"
    assert audit["context_results"]["invisible-identity"]["status"] == "NOT_DISTINGUISHABLE"
    assert audit["all_effects_visible"] is False
    assert audit["all_contexts_pairwise_distinguishable"] is False


def test_identical_duplicate_interventions_are_audited_as_redundant_not_conflicting():
    ledger = load_ledger(ROOT / "examples" / "fdcs_soft_interventions.yaml")
    audit = audit_intervention_set(ledger, [
        {"id": "a", "kind": "do_set", "target_tx_id": "root", "value": 4},
        {"id": "b", "kind": "do_set", "target_tx_id": "root", "value": 4},
    ])
    assert audit["status"] == "WARN"
    assert len(audit["conflicts"]) == 0
    assert len(audit["redundancies"]) == 1
    assert len(audit["executable_interventions"]) == 1
