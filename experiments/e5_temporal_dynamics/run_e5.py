from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmlc.runtime import Runtime
from mmlc.types import (
    AuditPolicy,
    CorrectionEntry,
    FixedPointGroup,
    MatrixLedger,
    TemporalRef,
    Transaction,
    ValueRef,
)


def temporal_experiment(rng: random.Random) -> dict:
    ledgers = 64
    periods = 64
    total_cells = 0
    correct_cells = 0
    fdcs_weight_checks = 0
    fdcs_weight_failures = 0
    elapsed = 0.0
    for ledger_index in range(ledgers):
        start = rng.randint(-20, 20)
        increments = [rng.randint(-5, 5) for _ in range(periods - 1)]
        transactions = {}
        expected = [start]
        transactions["x-000"] = Transaction(
            tx_id="x-000", source_id=None, base=start, operator="identity",
            declared_result=start, time_index=0, series_id="X",
        )
        for t in range(1, periods):
            expected.append(expected[-1] + increments[t - 1])
            tx_id = f"x-{t:03d}"
            transactions[tx_id] = Transaction(
                tx_id=tx_id,
                source_id=None,
                base=TemporalRef("X", lag=1),
                operator="add",
                operand=increments[t - 1],
                declared_result=expected[-1],
                time_index=t,
                series_id="X",
            )
        ledger = MatrixLedger(
            ledger_id=f"temporal-{ledger_index}", version="0.5", sources={},
            transactions=transactions, display_order=list(transactions), traversals={},
            audit_policy=AuditPolicy(), fdcs={
                "enabled": True,
                "context": "e5-random",
                "decay_lambda": 0.93,
                "context_modulation": 1.0,
            },
        )
        began = time.perf_counter()
        result = Runtime().execute(ledger, deterministic=True)
        elapsed += time.perf_counter() - began
        for t, tx_id in enumerate(transactions):
            total_cells += 1
            if result.transactions[tx_id].computed_result == expected[t] and result.transactions[tx_id].status == "PASS":
                correct_cells += 1
        for edge in result.fdcs_projection["edges"]:
            if edge["lag"] > 0:
                fdcs_weight_checks += 1
                expected_weight = 0.93 ** edge["lag"]
                if abs(edge["effective_weight"] - expected_weight) > 1e-12:
                    fdcs_weight_failures += 1
    return {
        "ledgers": ledgers,
        "periods_per_ledger": periods,
        "total_cells": total_cells,
        "correct_cells": correct_cells,
        "accuracy": correct_cells / total_cells,
        "fdcs_weight_checks": fdcs_weight_checks,
        "fdcs_weight_failures": fdcs_weight_failures,
        "elapsed_seconds": elapsed,
        "transactions_per_second": total_cells / elapsed,
    }


def fixed_point_experiment(rng: random.Random) -> dict:
    convergent_cases = 128
    divergent_cases = 32
    converged = 0
    value_passes = 0
    iterations = []
    elapsed = 0.0
    for index in range(convergent_cases):
        a = rng.uniform(-0.8, 0.8)
        c = rng.uniform(-0.8, 0.8)
        b = rng.uniform(-3.0, 3.0)
        d = rng.uniform(-3.0, 3.0)
        denom = 1.0 - a * c
        x_star = (a * d + b) / denom
        y_star = c * x_star + d
        txs = {
            "x": Transaction("x", None, ValueRef("y"), "affine", b, x_star, {"scale": a}),
            "y": Transaction("y", None, ValueRef("x"), "affine", d, y_star, {"scale": c}),
        }
        ledger = MatrixLedger(
            ledger_id=f"fixed-{index}", version="0.5", sources={}, transactions=txs,
            display_order=["x", "y"], traversals={},
            audit_policy=AuditPolicy(numeric_tolerance=1e-9),
            fixed_point_groups=[FixedPointGroup(
                group_id="xy", members=("x", "y"), tolerance=1e-12,
                max_iterations=500, initial_values={"x": 0.0, "y": 0.0},
            )],
        )
        began = time.perf_counter()
        result = Runtime().execute(ledger, deterministic=True)
        elapsed += time.perf_counter() - began
        group = result.fixed_point_analysis["groups"]["xy"]
        if group["converged"]:
            converged += 1
        iterations.append(group["iterations"])
        if (
            abs(float(result.transactions["x"].computed_result) - x_star) < 1e-8
            and abs(float(result.transactions["y"].computed_result) - y_star) < 1e-8
            and result.global_audit["status"] == "PASS"
        ):
            value_passes += 1

    divergent_detected = 0
    for index in range(divergent_cases):
        a = rng.uniform(1.05, 1.30)
        c = rng.uniform(1.05, 1.30)
        txs = {
            "x": Transaction("x", None, ValueRef("y"), "affine", 1.0, None, {"scale": a}),
            "y": Transaction("y", None, ValueRef("x"), "affine", 1.0, None, {"scale": c}),
        }
        ledger = MatrixLedger(
            ledger_id=f"divergent-{index}", version="0.5", sources={}, transactions=txs,
            display_order=["x", "y"], traversals={}, audit_policy=AuditPolicy(),
            fixed_point_groups=[FixedPointGroup(
                group_id="xy", members=("x", "y"), tolerance=1e-12,
                max_iterations=30, initial_values={"x": 0.0, "y": 0.0},
            )],
        )
        result = Runtime().execute(ledger, deterministic=True)
        if not result.fixed_point_analysis["groups"]["xy"]["converged"] and result.global_audit["status"] == "FAIL":
            divergent_detected += 1
    return {
        "convergent_cases": convergent_cases,
        "converged": converged,
        "value_passes": value_passes,
        "convergence_accuracy": value_passes / convergent_cases,
        "mean_iterations": sum(iterations) / len(iterations),
        "max_iterations_observed": max(iterations),
        "divergent_cases": divergent_cases,
        "divergent_detected": divergent_detected,
        "divergence_detection_accuracy": divergent_detected / divergent_cases,
        "elapsed_seconds_convergent": elapsed,
    }


def correction_experiment(rng: random.Random) -> dict:
    cases = 256
    passed = 0
    originals_preserved = 0
    deterministic_heads = 0
    chain_links_valid = 0
    for index in range(cases):
        base = rng.randint(-20, 20)
        operand = rng.randint(-20, 20)
        truth = base + operand
        wrong = truth + rng.choice([-7, -3, 2, 5])
        intermediate = wrong + rng.choice([-2, 1, 4])
        tx = Transaction("claim", None, base, "add", operand, wrong)
        ledger = MatrixLedger(
            ledger_id=f"correction-{index}", version="0.5", sources={},
            transactions={"claim": tx}, display_order=["claim"], traversals={},
            audit_policy=AuditPolicy(), corrections=[
                CorrectionEntry("c1", "claim", "declared_result", "replace", intermediate, "provisional"),
                CorrectionEntry("c2", "claim", "declared_result", "replace", truth, "verified"),
            ],
        )
        result = Runtime().execute(ledger, deterministic=True)
        again = Runtime().execute(ledger, deterministic=True)
        entries = result.correction_analysis["entries"]
        if result.transactions["claim"].status == "PASS" and result.transactions["claim"].effective_declared_result == truth:
            passed += 1
        if ledger.transactions["claim"].declared_result == wrong and result.transactions["claim"].original_declared_result == wrong:
            originals_preserved += 1
        if result.correction_analysis["head_hash"] == again.correction_analysis["head_hash"]:
            deterministic_heads += 1
        if len(entries) == 2 and entries[1].previous_hash == entries[0].entry_hash:
            chain_links_valid += 1
    return {
        "cases": cases,
        "passed": passed,
        "originals_preserved": originals_preserved,
        "deterministic_heads": deterministic_heads,
        "chain_links_valid": chain_links_valid,
        "accuracy": passed / cases,
    }


def main() -> None:
    rng = random.Random(20260722)
    began = time.perf_counter()
    temporal = temporal_experiment(rng)
    fixed_point = fixed_point_experiment(rng)
    corrections = correction_experiment(rng)
    metrics = {
        "experiment": "E5 temporal dynamics, fixed points, immutable corrections and FDCS projection",
        "seed": 20260722,
        "temporal": temporal,
        "fixed_point": fixed_point,
        "corrections": corrections,
        "overall_pass": (
            temporal["accuracy"] == 1.0
            and temporal["fdcs_weight_failures"] == 0
            and fixed_point["convergence_accuracy"] == 1.0
            and fixed_point["divergence_detection_accuracy"] == 1.0
            and corrections["accuracy"] == 1.0
            and corrections["originals_preserved"] == corrections["cases"]
        ),
        "wall_seconds": time.perf_counter() - began,
        "scope_limits": [
            "Temporal references use discrete integer time indices.",
            "Only explicitly declared Jacobi fixed-point groups are allowed.",
            "Convergence is numerical evidence under a tolerance, not a general proof.",
            "Corrections currently target declared_result only.",
            "FDCS support is a projection interface; declared interventions are not executed in v0.5.",
        ],
    }
    out = ROOT / "outputs" / "e5_temporal_dynamics"
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
