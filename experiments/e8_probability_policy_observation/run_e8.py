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

from mmlc.runtime import Runtime
from mmlc.types import AuditPolicy, MatrixLedger, Transaction, ValueRef

OUT = ROOT / "outputs" / "e8_probability_policy_observation"
OUT.mkdir(parents=True, exist_ok=True)
RNG = random.Random(20260723)


def policy_ledger(index: int, policies: int = 4, scenarios: int = 4):
    contexts = []
    expected = {}
    risk = RNG.choice([0.0, 0.1, 0.25, 0.5])
    cost_weight = RNG.choice([0.5, 1.0, 1.5])
    for p in range(policies):
        policy_id = f"policy-{p}"
        raw = [RNG.uniform(0.1, 1.0) for _ in range(scenarios)]
        total = sum(raw)
        probs = [value / total for value in raw]
        outcomes = [RNG.uniform(-10.0, 30.0) for _ in range(scenarios)]
        cost = RNG.uniform(0.0, 5.0)
        mean = sum(prob * value for prob, value in zip(probs, outcomes))
        variance = sum(prob * (value - mean) ** 2 for prob, value in zip(probs, outcomes))
        score = mean - risk * math.sqrt(max(0.0, variance)) - cost_weight * cost
        expected[policy_id] = {
            "mean": mean, "variance": variance, "cost": cost, "score": score,
        }
        for s, (probability, outcome) in enumerate(zip(probs, outcomes)):
            context_id = f"{policy_id}-scenario-{s}"
            contexts.append({
                "id": context_id,
                "policy_id": policy_id,
                "scenario_id": f"scenario-{s}",
                "probability": probability,
                "cost": cost,
                "interventions": [{
                    "id": f"set-{context_id}", "kind": "do_set",
                    "target_tx_id": "outcome", "value": outcome,
                }],
            })
    ledger = MatrixLedger(
        ledger_id=f"e8-policy-{index}", version="0.8", sources={},
        transactions={"outcome": Transaction("outcome", None, 0.0, "identity")},
        display_order=["outcome"], layout=[["outcome"]],
        traversals={"execute": "dependency_topological"}, audit_policy=AuditPolicy(),
        fdcs={
            "enabled": True, "base_context": "observed", "parallel_workers": 8,
            "contexts": contexts,
            "probability_model": {"tolerance": 1e-10},
            "policy_selection": {
                "enabled": True, "risk_aversion": risk, "cost_weight": cost_weight,
                "objectives": [{"tx_id": "outcome", "direction": "maximize", "weight": 1.0}],
            },
        },
    )
    return ledger, expected


def observation_ledger(index: int, impossible: bool = False) -> MatrixLedger:
    seed = RNG.randint(1, 20)
    txs = {
        "seed": Transaction("seed", None, seed, "identity"),
        "root": Transaction("root", None, ValueRef("seed"), "add", 1),
        "mid": Transaction("mid", None, ValueRef("root"), "multiply", 2),
        "leaf": Transaction("leaf", None, ValueRef("mid"), "identity"),
    }
    target = seed + RNG.randint(2, 8)
    if impossible:
        contexts = [
            {"id": "hard", "interventions": [{
                "id": "hard-root", "kind": "do_set", "target_tx_id": "root", "value": target,
            }]},
            {"id": "soft", "interventions": [{
                "id": "soft-root", "kind": "soft_shift", "target_tx_id": "root",
                "shift": target - (seed + 1),
            }]},
        ]
    else:
        contexts = [
            {"id": "root-policy", "interventions": [{
                "id": "hard-root", "kind": "do_set", "target_tx_id": "root", "value": target,
            }]},
            {"id": "mid-policy", "interventions": [{
                "id": "hard-mid", "kind": "do_set", "target_tx_id": "mid", "value": target * 2,
            }]},
        ]
    return MatrixLedger(
        ledger_id=f"e8-observe-{index}-{'impossible' if impossible else 'found'}",
        version="0.8", sources={}, transactions=txs,
        display_order=list(txs), layout=[list(txs)],
        traversals={"execute": "dependency_topological"}, audit_policy=AuditPolicy(),
        fdcs={
            "enabled": True, "base_context": "observed", "observed_transactions": ["leaf"],
            "contexts": contexts,
            "observation_planning": {
                "enabled": True, "candidate_transactions": ["seed", "root", "mid"],
                "max_additional_observations": 2, "max_solutions": 8,
            },
        },
    )


def main() -> None:
    runtime = Runtime()
    started = time.perf_counter()
    policy_ledgers = 64
    policy_groups = 0
    branch_count = 0
    probability_errors = 0
    moment_errors = 0
    selection_errors = 0
    deterministic_hash_errors = 0

    for i in range(policy_ledgers):
        ledger, expected = policy_ledger(i)
        first = runtime.execute(ledger, deterministic=True)
        second = runtime.execute(ledger, deterministic=True)
        probability = first.fdcs_projection["probability_analysis"]
        policy = first.fdcs_projection["policy_analysis"]
        policy_groups += len(expected)
        branch_count += sum(len(group["contexts"]) for group in probability["groups"].values())
        if probability["status"] != "PASS":
            probability_errors += 1
        if probability["analysis_hash"] != second.fdcs_projection["probability_analysis"]["analysis_hash"]:
            deterministic_hash_errors += 1
        if policy["analysis_hash"] != second.fdcs_projection["policy_analysis"]["analysis_hash"]:
            deterministic_hash_errors += 1
        for policy_id, values in expected.items():
            group = probability["groups"][policy_id]
            uncertainty = group["transaction_uncertainty"]["outcome"]
            actual = policy["policies"][policy_id]
            if abs(group["probability_sum"] - 1.0) > 1e-9:
                probability_errors += 1
            if abs(uncertainty["expected_value"] - values["mean"]) > 1e-9:
                moment_errors += 1
            if abs(uncertainty["variance"] - values["variance"]) > 1e-8:
                moment_errors += 1
            if abs(actual["score"] - values["score"]) > 1e-8:
                selection_errors += 1
        best = max(item["score"] for item in expected.values())
        expected_selected = sorted(k for k, v in expected.items() if abs(v["score"] - best) <= 1e-12)
        if policy["selected_policies"] != expected_selected:
            selection_errors += 1

    found_ledgers = 64
    impossible_ledgers = 32
    observation_found_errors = 0
    observation_impossible_errors = 0
    searched_sets = 0
    for i in range(found_ledgers):
        result = runtime.execute(observation_ledger(i), deterministic=True)
        plan = result.fdcs_projection["observation_plan"]
        searched_sets += int(plan.get("searched_candidate_sets", 0))
        if plan["status"] != "FOUND" or plan["minimum_size"] != 1 or plan["solutions"] != [["root"]]:
            observation_found_errors += 1
    for i in range(impossible_ledgers):
        result = runtime.execute(observation_ledger(i, impossible=True), deterministic=True)
        plan = result.fdcs_projection["observation_plan"]
        if plan["status"] != "IMPOSSIBLE" or not plan.get("impossible_pairs"):
            observation_impossible_errors += 1

    elapsed = time.perf_counter() - started
    total_errors = sum([
        probability_errors, moment_errors, selection_errors, deterministic_hash_errors,
        observation_found_errors, observation_impossible_errors,
    ])
    metrics = {
        "experiment": "E8 probabilistic branches, uncertainty propagation, policy selection and observation planning",
        "seed": 20260723,
        "status": "PASS" if total_errors == 0 else "FAIL",
        "elapsed_seconds": elapsed,
        "probability_policy": {
            "ledgers": policy_ledgers,
            "policy_groups": policy_groups,
            "probabilistic_branches": branch_count,
            "probability_errors": probability_errors,
            "moment_errors": moment_errors,
            "selection_errors": selection_errors,
            "deterministic_hash_errors": deterministic_hash_errors,
            "accuracy": 1.0 if policy_groups == 0 else 1.0 - (probability_errors + moment_errors + selection_errors) / (policy_groups * 4),
        },
        "observation_planning": {
            "found_ledgers": found_ledgers,
            "found_errors": observation_found_errors,
            "minimum_size_one": found_ledgers - observation_found_errors,
            "impossible_ledgers": impossible_ledgers,
            "impossible_errors": observation_impossible_errors,
            "searched_candidate_sets": searched_sets,
            "accuracy": 1.0 - (observation_found_errors + observation_impossible_errors) / (found_ledgers + impossible_ledgers),
        },
        "scope_note": (
            "E8 tests declared discrete branch probabilities and exact finite observation planning inside supplied models. "
            "It does not estimate probabilities from data or establish external causal truth."
        ),
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False, default=str))
    if total_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
