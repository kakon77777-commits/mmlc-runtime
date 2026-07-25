from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmlc.fdcs import audit_intervention_set
from mmlc.runtime import Runtime
from mmlc.types import AuditPolicy, FixedPointGroup, MatrixLedger, Transaction, ValueRef

OUT = ROOT / "outputs" / "e7_soft_cyclic_identifiability"
OUT.mkdir(parents=True, exist_ok=True)
RNG = random.Random(20260722)


def chain_ledger(index: int, length: int = 32) -> tuple[MatrixLedger, int, float, float]:
    txs: dict[str, Transaction] = {}
    txs["t00"] = Transaction("t00", None, RNG.randint(1, 5), "identity")
    for i in range(1, length):
        txs[f"t{i:02d}"] = Transaction(
            f"t{i:02d}", None, ValueRef(f"t{i-1:02d}"), "add", RNG.randint(-3, 7)
        )
    target_index = RNG.randint(2, length - 3)
    scale = RNG.choice([0.5, 1.25, 1.5, 2.0])
    shift = RNG.randint(-4, 5)
    target = f"t{target_index:02d}"
    ledger = MatrixLedger(
        ledger_id=f"e7-soft-chain-{index}", version="0.7", sources={}, transactions=txs,
        display_order=list(txs), traversals={"execute": "dependency_topological"},
        audit_policy=AuditPolicy(), layout=[list(txs)],
        fdcs={
            "enabled": True,
            "base_context": "observed",
            "contexts": [{
                "id": "soft",
                "interventions": [{
                    "id": "soft-target", "kind": "soft_affine", "target_tx_id": target,
                    "scale": scale, "shift": shift,
                }],
            }],
        },
    )
    return ledger, target_index, scale, shift


def fixed_ledger(index: int) -> tuple[MatrixLedger, dict[str, float]]:
    a = RNG.uniform(0.1, 0.55)
    c = RNG.uniform(0.1, 0.55)
    b = RNG.uniform(-2.0, 3.0)
    d = RNG.uniform(-2.0, 3.0)
    hard = RNG.uniform(-4.0, 5.0)
    soft_scale = RNG.uniform(0.6, 1.25)
    # Keep the transformed Jacobi map contractive.
    if abs(soft_scale * a * c) >= 0.75:
        soft_scale = 0.75 / max(abs(a * c), 1e-9) * 0.8
    soft_shift = RNG.uniform(-1.5, 1.5)
    txs = {
        "x": Transaction("x", None, ValueRef("y"), "affine", b, context={"scale": a}),
        "y": Transaction("y", None, ValueRef("x"), "affine", d, context={"scale": c}),
    }
    ledger = MatrixLedger(
        ledger_id=f"e7-fixed-{index}", version="0.7", sources={}, transactions=txs,
        display_order=["x", "y"], traversals={"execute": "dependency_topological"},
        audit_policy=AuditPolicy(numeric_tolerance=1e-9), layout=[["x", "y"]],
        fixed_point_groups=[FixedPointGroup(
            group_id="xy", members=("x", "y"), tolerance=1e-12, max_iterations=500,
            initial_values={"x": 0.0, "y": 0.0},
        )],
        fdcs={
            "enabled": True,
            "base_context": "observed",
            "parallel_workers": 2,
            "contexts": [
                {"id": "hard", "interventions": [{
                    "id": "hard-x", "kind": "do_set", "target_tx_id": "x", "value": hard,
                }]},
                {"id": "soft", "interventions": [{
                    "id": "soft-x", "kind": "soft_affine", "target_tx_id": "x",
                    "scale": soft_scale, "shift": soft_shift,
                }]},
            ],
        },
    )
    expected = {
        "hard_x": hard,
        "hard_y": c * hard + d,
    }
    denominator = 1.0 - soft_scale * a * c
    expected["soft_x"] = (soft_scale * (a * d + b) + soft_shift) / denominator
    expected["soft_y"] = c * expected["soft_x"] + d
    return ledger, expected


def ident_ledger(index: int) -> MatrixLedger:
    seed = RNG.randint(1, 9)
    target_value = seed + RNG.randint(2, 7)
    baseline_root = seed + 1
    shift = target_value - baseline_root
    txs = {
        "seed": Transaction("seed", None, seed, "identity"),
        "root": Transaction("root", None, ValueRef("seed"), "add", 1),
        "leaf": Transaction("leaf", None, ValueRef("root"), "multiply", 2),
    }
    return MatrixLedger(
        ledger_id=f"e7-ident-{index}", version="0.7", sources={}, transactions=txs,
        display_order=["seed", "root", "leaf"], traversals={"execute": "dependency_topological"},
        audit_policy=AuditPolicy(), layout=[["seed", "root", "leaf"]],
        fdcs={
            "enabled": True,
            "base_context": "observed",
            "observed_transactions": ["leaf"],
            "parallel_workers": 3,
            "contexts": [
                {"id": "hard", "interventions": [{
                    "id": "hard-root", "kind": "do_set", "target_tx_id": "root", "value": target_value,
                }]},
                {"id": "soft-equivalent", "interventions": [{
                    "id": "soft-root", "kind": "soft_shift", "target_tx_id": "root", "shift": shift,
                }]},
                {"id": "identity", "interventions": [{
                    "id": "identity-leaf", "kind": "soft_affine", "target_tx_id": "leaf", "scale": 1, "shift": 0,
                }]},
                {"id": "conflict", "interventions": [
                    {"id": "c1", "kind": "do_set", "target_tx_id": "root", "value": target_value},
                    {"id": "c2", "kind": "do_set", "target_tx_id": "root", "value": target_value + 1},
                ]},
            ],
        },
    )


def main() -> None:
    runtime = Runtime()
    started = time.perf_counter()

    soft_ledgers = 64
    soft_value_checks = 0
    soft_value_errors = 0
    soft_cut_errors = 0
    soft_edge_preservation_errors = 0
    diff_chain_errors = 0
    diff_replay_errors = 0
    for i in range(soft_ledgers):
        ledger, target_index, scale, shift = chain_ledger(i)
        first = runtime.execute(ledger, deterministic=True)
        second = runtime.execute(ledger, deterministic=True)
        baseline = first.fdcs_projection["contexts"]["observed"]["values"]
        branch = first.fdcs_projection["contexts"]["soft"]
        values = branch["values"]
        target = f"t{target_index:02d}"
        expected_target = scale * baseline[target] + shift
        propagated_delta = expected_target - baseline[target]
        for j in range(32):
            tx_id = f"t{j:02d}"
            expected = baseline[tx_id] if j < target_index else baseline[tx_id] + propagated_delta
            soft_value_checks += 1
            if not math.isclose(float(values[tx_id]), float(expected), rel_tol=1e-10, abs_tol=1e-10):
                soft_value_errors += 1
        if branch["cut_edges"]:
            soft_cut_errors += 1
        edge_pairs = {(e["source"], e["target"]) for e in branch["projection"]["edges"]}
        if (f"t{target_index-1:02d}", target) not in edge_pairs:
            soft_edge_preservation_errors += 1
        diff = branch["differential_ledger"]
        previous = "0" * 64
        for record in diff["records"]:
            if record["previous_hash"] != previous:
                diff_chain_errors += 1
            previous = record["entry_hash"]
        if previous != diff["head_hash"]:
            diff_chain_errors += 1
        if diff["head_hash"] != second.fdcs_projection["contexts"]["soft"]["differential_ledger"]["head_hash"]:
            diff_replay_errors += 1

    fixed_systems = 64
    fixed_value_checks = 0
    fixed_value_errors = 0
    fixed_convergence_errors = 0
    fixed_cut_errors = 0
    for i in range(fixed_systems):
        ledger, expected = fixed_ledger(i)
        result = runtime.execute(ledger, deterministic=True)
        for context_id, x_key, y_key in [
            ("hard", "hard_x", "hard_y"),
            ("soft", "soft_x", "soft_y"),
        ]:
            branch = result.fdcs_projection["contexts"][context_id]
            fixed_value_checks += 2
            if not math.isclose(float(branch["values"]["x"]), expected[x_key], rel_tol=1e-8, abs_tol=1e-8):
                fixed_value_errors += 1
            if not math.isclose(float(branch["values"]["y"]), expected[y_key], rel_tol=1e-8, abs_tol=1e-8):
                fixed_value_errors += 1
            groups = branch["projection"]
            if branch["global_audit"] != "PASS":
                fixed_convergence_errors += 1
        if len(result.fdcs_projection["contexts"]["hard"]["cut_edges"]) != 1:
            fixed_cut_errors += 1
        if result.fdcs_projection["contexts"]["soft"]["cut_edges"]:
            fixed_cut_errors += 1

    audit_cases = 256
    conflict_tp = conflict_fp = redundancy_tp = redundancy_fp = 0
    dummy, _, _, _ = chain_ledger(9999, 8)
    for i in range(audit_cases):
        if i % 2 == 0:
            raw = [
                {"id": f"a{i}", "kind": "do_set", "target_tx_id": "t02", "value": 4},
                {"id": f"b{i}", "kind": "do_set", "target_tx_id": "t02", "value": 5},
            ]
            audit = audit_intervention_set(dummy, raw)
            conflict_tp += int(audit["status"] == "FAIL" and len(audit["conflicts"]) == 1)
            redundancy_fp += int(bool(audit["redundancies"]))
        else:
            raw = [
                {"id": f"a{i}", "kind": "do_set", "target_tx_id": "t02", "value": 4},
                {"id": f"b{i}", "kind": "do_set", "target_tx_id": "t02", "value": 4},
            ]
            audit = audit_intervention_set(dummy, raw)
            redundancy_tp += int(audit["status"] == "WARN" and len(audit["redundancies"]) == 1)
            conflict_fp += int(bool(audit["conflicts"]))

    ident_ledgers = 64
    equivalent_class_errors = 0
    invisible_effect_errors = 0
    conflict_isolation_errors = 0
    for i in range(ident_ledgers):
        result = runtime.execute(ident_ledger(i), deterministic=True)
        fdcs = result.fdcs_projection
        ident = fdcs["identifiability_audit"]
        if ["hard", "soft-equivalent"] not in ident["equivalence_classes"]:
            equivalent_class_errors += 1
        if ident["context_results"]["identity"]["status"] != "NOT_DISTINGUISHABLE":
            invisible_effect_errors += 1
        if fdcs["contexts"]["conflict"]["status"] != "CONFLICT" or fdcs["contexts"]["hard"]["status"] != "EXECUTED":
            conflict_isolation_errors += 1

    elapsed = time.perf_counter() - started
    metrics = {
        "experiment": "E7 soft interventions, cyclic re-solving, differential ledgers and identifiability",
        "seed": 20260722,
        "soft_intervention": {
            "ledgers": soft_ledgers,
            "transactions_per_ledger": 32,
            "value_checks": soft_value_checks,
            "value_errors": soft_value_errors,
            "accuracy": (soft_value_checks - soft_value_errors) / soft_value_checks,
            "unexpected_cut_edges": soft_cut_errors,
            "edge_preservation_errors": soft_edge_preservation_errors,
        },
        "fixed_point_intervention": {
            "systems": fixed_systems,
            "branches": fixed_systems * 2,
            "value_checks": fixed_value_checks,
            "value_errors": fixed_value_errors,
            "accuracy": (fixed_value_checks - fixed_value_errors) / fixed_value_checks,
            "convergence_errors": fixed_convergence_errors,
            "cut_contract_errors": fixed_cut_errors,
        },
        "differential_ledger": {
            "hash_chain_errors": diff_chain_errors,
            "deterministic_replay_errors": diff_replay_errors,
            "accuracy": 1.0 if diff_chain_errors == 0 and diff_replay_errors == 0 else 0.0,
        },
        "intervention_conflict_audit": {
            "cases": audit_cases,
            "conflict_true_positives": conflict_tp,
            "conflict_false_positives": conflict_fp,
            "redundancy_true_positives": redundancy_tp,
            "redundancy_false_positives": redundancy_fp,
            "accuracy": (conflict_tp + redundancy_tp) / audit_cases,
        },
        "ledger_identifiability": {
            "ledgers": ident_ledgers,
            "equivalence_class_errors": equivalent_class_errors,
            "invisible_effect_errors": invisible_effect_errors,
            "conflict_isolation_errors": conflict_isolation_errors,
            "accuracy": 1.0 if not (equivalent_class_errors or invisible_effect_errors or conflict_isolation_errors) else 0.0,
        },
        "elapsed_seconds": elapsed,
        "scope_limits": [
            "Identifiability means deterministic distinguishability on declared observed transactions, not statistical causal identification.",
            "Fixed-point intervention tests cover declared contractive two-variable Jacobi systems, not arbitrary nonlinear cycles.",
            "Soft interventions are affine output transformations of known structural equations.",
        ],
    }
    failures = (
        soft_value_errors + soft_cut_errors + soft_edge_preservation_errors + diff_chain_errors + diff_replay_errors
        + fixed_value_errors + fixed_convergence_errors + fixed_cut_errors + conflict_fp + redundancy_fp
        + equivalent_class_errors + invisible_effect_errors + conflict_isolation_errors
    )
    metrics["status"] = "PASS" if failures == 0 and conflict_tp == audit_cases // 2 and redundancy_tp == audit_cases // 2 else "FAIL"
    (OUT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if metrics["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
