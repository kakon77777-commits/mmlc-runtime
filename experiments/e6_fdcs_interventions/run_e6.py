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
from mmlc.types import AuditPolicy, MatrixLedger, Transaction, ValueRef


def expected_intervention_values(initial: int, increments: list[int], target: int, replacement: int) -> list[int]:
    values = [initial]
    for increment in increments:
        values.append(values[-1] + increment)
    values[target] = replacement
    for index in range(target + 1, len(values)):
        values[index] = values[index - 1] + increments[index - 1]
    return values


def intervention_experiment(rng: random.Random) -> dict:
    ledgers = 64
    length = 32
    branch_cell_checks = 0
    branch_cell_passes = 0
    cut_edge_checks = 0
    cut_edge_passes = 0
    ancestor_stability_checks = 0
    ancestor_stability_passes = 0
    independence_checks = 0
    independence_passes = 0
    deterministic_hash_checks = 0
    deterministic_hash_passes = 0
    elapsed = 0.0

    for ledger_index in range(ledgers):
        initial = rng.randint(-20, 20)
        increments = [rng.randint(-5, 7) for _ in range(length - 1)]
        observed = [initial]
        transactions: dict[str, Transaction] = {
            "n-00": Transaction("n-00", None, initial, "identity", declared_result=initial)
        }
        for index, increment in enumerate(increments, start=1):
            observed.append(observed[-1] + increment)
            tx_id = f"n-{index:02d}"
            transactions[tx_id] = Transaction(
                tx_id=tx_id,
                source_id=None,
                base=ValueRef(f"n-{index - 1:02d}"),
                operator="add",
                operand=increment,
                declared_result=observed[-1],
                context={"fractal_level": index % 4, "causal_weight": 1.0 + (index % 5) / 10},
            )

        targets = sorted(rng.sample(range(1, length - 1), 2))
        replacements = [rng.randint(-30, 30), rng.randint(-30, 30)]
        contexts = []
        expected_by_context: dict[str, list[int]] = {}
        for branch_index, (target, replacement) in enumerate(zip(targets, replacements), start=1):
            context_id = f"branch-{branch_index}"
            contexts.append({
                "id": context_id,
                "modulation": 0.8 + branch_index * 0.4,
                "interventions": [{
                    "id": f"do-{target}-{replacement}",
                    "kind": "do_set",
                    "target_tx_id": f"n-{target:02d}",
                    "value": replacement,
                }],
            })
            expected_by_context[context_id] = expected_intervention_values(
                initial, increments, target, replacement
            )
        contexts.append({"id": "weight-only", "modulation": 1.75, "interventions": []})

        ledger = MatrixLedger(
            ledger_id=f"e6-intervention-{ledger_index}",
            version="0.6",
            sources={},
            transactions=transactions,
            display_order=list(transactions),
            traversals={},
            audit_policy=AuditPolicy(),
            fdcs={
                "enabled": True,
                "base_context": "observed",
                "decay_lambda": 0.91,
                "fractal_decay_lambda": 0.83,
                "direction_weights": {"forward": 1.0, "reverse": 0.35},
                "parallel_workers": 3,
                "contexts": contexts,
            },
        )
        began = time.perf_counter()
        result = Runtime().execute(ledger, deterministic=True)
        elapsed += time.perf_counter() - began
        again = Runtime().execute(ledger, deterministic=True)
        fdcs = result.fdcs_projection

        for context_id, expected in expected_by_context.items():
            branch = fdcs["contexts"][context_id]
            intervention = next(item for item in contexts if item["id"] == context_id)["interventions"][0]
            target_index = int(intervention["target_tx_id"].split("-")[1])
            for index, expected_value in enumerate(expected):
                branch_cell_checks += 1
                if branch["values"][f"n-{index:02d}"] == expected_value:
                    branch_cell_passes += 1
            ancestor_stability_checks += target_index
            for index in range(target_index):
                if branch["values"][f"n-{index:02d}"] == observed[index]:
                    ancestor_stability_passes += 1
            cut_edge_checks += 1
            cuts = branch["cut_edges"]
            if (
                len(cuts) == 1
                and cuts[0]["source"] == f"n-{target_index - 1:02d}"
                and cuts[0]["target"] == f"n-{target_index:02d}"
            ):
                cut_edge_passes += 1

        weight_only = fdcs["contexts"]["weight-only"]
        independence_checks += length
        for index, value in enumerate(observed):
            if weight_only["values"][f"n-{index:02d}"] == value:
                independence_passes += 1

        deterministic_hash_checks += len(fdcs["contexts"])
        for context_id in fdcs["contexts"]:
            if (
                fdcs["contexts"][context_id]["semantic_hash"]
                == again.fdcs_projection["contexts"][context_id]["semantic_hash"]
            ):
                deterministic_hash_passes += 1

    return {
        "ledgers": ledgers,
        "transactions_per_ledger": length,
        "counterfactual_branches_per_ledger": 2,
        "weight_only_branches_per_ledger": 1,
        "branch_cell_checks": branch_cell_checks,
        "branch_cell_passes": branch_cell_passes,
        "branch_value_accuracy": branch_cell_passes / branch_cell_checks,
        "cut_edge_checks": cut_edge_checks,
        "cut_edge_passes": cut_edge_passes,
        "cut_edge_accuracy": cut_edge_passes / cut_edge_checks,
        "ancestor_stability_checks": ancestor_stability_checks,
        "ancestor_stability_passes": ancestor_stability_passes,
        "ancestor_stability_accuracy": ancestor_stability_passes / ancestor_stability_checks,
        "context_independence_checks": independence_checks,
        "context_independence_passes": independence_passes,
        "context_independence_accuracy": independence_passes / independence_checks,
        "deterministic_hash_checks": deterministic_hash_checks,
        "deterministic_hash_passes": deterministic_hash_passes,
        "deterministic_hash_accuracy": deterministic_hash_passes / deterministic_hash_checks,
        "elapsed_seconds": elapsed,
        "branch_transactions_per_second": branch_cell_checks / elapsed,
    }


def weight_experiment(rng: random.Random) -> dict:
    ledgers = 64
    length = 65
    edge_checks = 0
    forward_passes = 0
    reverse_passes = 0
    asymmetric_edges = 0
    fractal_gap_edges = 0
    temporal_lag_edges = 0

    for ledger_index in range(ledgers):
        transactions: dict[str, Transaction] = {}
        time_indices = [0]
        transactions["w-000"] = Transaction(
            "w-000", None, rng.randint(-5, 5), "identity",
            context={"fractal_level": rng.randint(0, 4)}, time_index=0,
        )
        for index in range(1, length):
            time_indices.append(time_indices[-1] + rng.randint(0, 3))
            base_weight = rng.uniform(0.2, 2.0)
            forward = rng.uniform(0.3, 1.7)
            reverse = rng.uniform(0.05, 0.9)
            transactions[f"w-{index:03d}"] = Transaction(
                tx_id=f"w-{index:03d}",
                source_id=None,
                base=ValueRef(f"w-{index - 1:03d}"),
                operator="add",
                operand=rng.randint(-2, 3),
                context={
                    "fractal_level": rng.randint(0, 4),
                    "causal_weight": base_weight,
                    "causal_weight_forward": forward,
                    "causal_weight_reverse": reverse,
                },
                time_index=time_indices[-1],
            )
        decay = rng.uniform(0.72, 0.98)
        fractal_decay = rng.uniform(0.60, 0.95)
        modulation = rng.uniform(0.5, 1.8)
        ledger = MatrixLedger(
            ledger_id=f"e6-weight-{ledger_index}", version="0.6", sources={},
            transactions=transactions, display_order=list(transactions), traversals={},
            audit_policy=AuditPolicy(), fdcs={
                "enabled": True,
                "base_context": "observed",
                "decay_lambda": decay,
                "fractal_decay_lambda": fractal_decay,
                "context_modulation": modulation,
                "direction_weights": {"forward": 9.0, "reverse": 9.0},
            },
        )
        result = Runtime().execute(ledger, deterministic=True)
        for edge in result.fdcs_projection["edges"]:
            edge_checks += 1
            child_context = transactions[edge["target"]].context
            expected_common = (
                float(child_context["causal_weight"])
                * decay ** edge["lag"]
                * fractal_decay ** edge["fractal_level_gap"]
                * modulation
            )
            expected_forward = expected_common * float(child_context["causal_weight_forward"])
            expected_reverse = expected_common * float(child_context["causal_weight_reverse"])
            if abs(edge["forward_effective_weight"] - expected_forward) <= 1e-12:
                forward_passes += 1
            if abs(edge["reverse_effective_weight"] - expected_reverse) <= 1e-12:
                reverse_passes += 1
            if abs(expected_forward - expected_reverse) > 1e-12:
                asymmetric_edges += 1
            if edge["fractal_level_gap"] > 0:
                fractal_gap_edges += 1
            if edge["lag"] > 0:
                temporal_lag_edges += 1

    return {
        "ledgers": ledgers,
        "edges_per_ledger": length - 1,
        "edge_checks": edge_checks,
        "forward_weight_passes": forward_passes,
        "reverse_weight_passes": reverse_passes,
        "forward_accuracy": forward_passes / edge_checks,
        "reverse_accuracy": reverse_passes / edge_checks,
        "asymmetric_edges": asymmetric_edges,
        "fractal_gap_edges": fractal_gap_edges,
        "temporal_lag_edges": temporal_lag_edges,
    }


def main() -> None:
    rng = random.Random(20260722)
    began = time.perf_counter()
    interventions = intervention_experiment(rng)
    weights = weight_experiment(rng)
    metrics = {
        "experiment": "E6 executable FDCS interventions, multicontext evolution, directional asymmetry and fractal decay",
        "seed": 20260722,
        "interventions": interventions,
        "weights": weights,
        "overall_pass": (
            interventions["branch_value_accuracy"] == 1.0
            and interventions["cut_edge_accuracy"] == 1.0
            and interventions["ancestor_stability_accuracy"] == 1.0
            and interventions["context_independence_accuracy"] == 1.0
            and interventions["deterministic_hash_accuracy"] == 1.0
            and weights["forward_accuracy"] == 1.0
            and weights["reverse_accuracy"] == 1.0
            and weights["asymmetric_edges"] == weights["edge_checks"]
        ),
        "wall_seconds": time.perf_counter() - began,
        "scope_limits": [
            "v0.6 executes only literal do_set interventions.",
            "Incoming edges are cut only for the intervened transaction; descendants are recomputed from existing structural equations.",
            "Interventions inside fixed-point groups are rejected.",
            "Context branches are independent counterfactual executions; they are not probabilities or learned possible worlds.",
            "Reverse weights are reverse traversal/query weights, not evidence of reverse causation.",
            "Fractal decay uses declared integer levels and does not infer a hierarchy.",
        ],
    }
    out = ROOT / "outputs" / "e6_fdcs_interventions"
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
