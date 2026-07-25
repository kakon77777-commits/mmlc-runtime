from __future__ import annotations

import json
import math
import random
import sys
import time
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmlc.errors import FDCSConfigurationError
from mmlc.parser import load_ledger
from mmlc.runtime import Runtime
from mmlc.types import AuditPolicy, MatrixLedger, Transaction, ValueRef

OUT = ROOT / "outputs" / "e9_continuous_information_decision"
OUT.mkdir(parents=True, exist_ok=True)
RNG = random.Random(20260723)


def continuous_ledger(index: int, samples: int = 256):
    mean_a = RNG.uniform(-5.0, 5.0)
    mean_b = RNG.uniform(-5.0, 5.0)
    sd_a = RNG.uniform(0.4, 2.0)
    sd_b = RNG.uniform(0.4, 2.0)
    correlation = RNG.uniform(-0.75, 0.75)
    txs = {
        "a": Transaction("a", None, 0.0, "identity"),
        "b": Transaction("b", None, 0.0, "identity"),
        "sum": Transaction("sum", None, ValueRef("a"), "add", ValueRef("b")),
    }
    ledger = MatrixLedger(
        ledger_id=f"e9-continuous-{index}", version="0.9", sources={}, transactions=txs,
        display_order=list(txs), layout=[list(txs)], traversals={"execute": "dependency_topological"},
        audit_policy=AuditPolicy(),
        fdcs={
            "enabled": True, "base_context": "observed", "parallel_workers": 8,
            "probability_model": {"tolerance": 1e-10},
            "continuous_uncertainty": {
                "enabled": True, "max_samples": 1024,
                "ensembles": [{
                    "id": "joint", "policy_id": "joint", "samples": samples,
                    "correlation_matrix": [[1.0, correlation], [correlation, 1.0]],
                    "variables": [
                        {"id": "a", "target_tx_id": "a", "distribution": "normal", "mean": mean_a, "stddev": sd_a},
                        {"id": "b", "target_tx_id": "b", "distribution": "normal", "mean": mean_b, "stddev": sd_b},
                    ],
                }],
            },
        },
    )
    return ledger, {"mean_a": mean_a, "mean_b": mean_b, "sd_a": sd_a, "sd_b": sd_b, "correlation": correlation}


def main() -> None:
    runtime = Runtime()
    started = time.perf_counter()

    continuous_ledgers = 32
    continuous_branches = 0
    mean_errors = 0
    stddev_errors = 0
    correlation_errors = 0
    probability_errors = 0
    deterministic_hash_errors = 0
    invalid_correlation_rejections = 0

    for index in range(continuous_ledgers):
        ledger, expected = continuous_ledger(index)
        first = runtime.execute(ledger, deterministic=True)
        second = runtime.execute(ledger, deterministic=True)
        continuous = first.fdcs_projection["continuous_approximation_analysis"]
        ensemble = continuous["ensembles"]["joint"]
        empirical = ensemble["empirical"]
        group = first.fdcs_projection["probability_analysis"]["groups"]["joint"]
        continuous_branches += ensemble["sample_count"]
        if abs(empirical["means"]["a"] - expected["mean_a"]) > 1e-10:
            mean_errors += 1
        if abs(empirical["means"]["b"] - expected["mean_b"]) > 1e-10:
            mean_errors += 1
        if abs(empirical["standard_deviations"]["a"] - expected["sd_a"]) / expected["sd_a"] > 0.05:
            stddev_errors += 1
        if abs(empirical["standard_deviations"]["b"] - expected["sd_b"]) / expected["sd_b"] > 0.08:
            stddev_errors += 1
        if abs(empirical["correlation_matrix"][0][1] - expected["correlation"]) > 0.06:
            correlation_errors += 1
        if group["status"] != "PASS" or abs(group["probability_sum"] - 1.0) > 1e-10:
            probability_errors += 1
        expected_sum = expected["mean_a"] + expected["mean_b"]
        actual_sum = group["transaction_uncertainty"]["sum"]["expected_value"]
        if abs(actual_sum - expected_sum) > 1e-9:
            mean_errors += 1
        if continuous["analysis_hash"] != second.fdcs_projection["continuous_approximation_analysis"]["analysis_hash"]:
            deterministic_hash_errors += 1

        broken = deepcopy(ledger)
        broken.fdcs = deepcopy(ledger.fdcs)
        broken.fdcs["continuous_uncertainty"]["ensembles"][0]["correlation_matrix"] = [[1.0, 1.2], [1.2, 1.0]]
        try:
            runtime.execute(broken, deterministic=True)
        except FDCSConfigurationError:
            invalid_correlation_rejections += 1

    sequential_cases = 32
    information_value_errors = 0
    sequential_errors = 0
    information_hash_errors = 0
    template = load_ledger(ROOT / "examples" / "fdcs_sequential_information_value.yaml")
    for _ in range(sequential_cases):
        first = runtime.execute(template, deterministic=True)
        second = runtime.execute(template, deterministic=True)
        info = first.fdcs_projection["information_value_analysis"]
        if abs(info["prior_best_value"] - 3.0) > 1e-12:
            information_value_errors += 1
        for candidate in ("signal_a", "signal_b"):
            row = info["candidate_information_values"][candidate]
            if abs(row["gross_information_value"] - 3.0) > 1e-12 or abs(row["net_information_value"] - 2.5) > 1e-12:
                information_value_errors += 1
        if info["decision_tree"].get("action") != "observe" or abs(info["sequential_expected_value"] - 11.0) > 1e-12:
            sequential_errors += 1
        if not all(branch["next"].get("action") == "observe" for branch in info["decision_tree"].get("branches", [])):
            sequential_errors += 1
        if info["analysis_hash"] != second.fdcs_projection["information_value_analysis"]["analysis_hash"]:
            information_hash_errors += 1

    cost_cases = 64
    cost_plan_errors = 0
    cost_template = load_ledger(ROOT / "examples" / "fdcs_cost_aware_observation.yaml")
    for _ in range(cost_cases):
        plan = runtime.execute(cost_template, deterministic=True).fdcs_projection["observation_plan"]
        if plan.get("solutions") != [["z"]] or plan.get("minimum_cost_solutions") != [["x", "y"]]:
            cost_plan_errors += 1
        if abs(float(plan.get("minimum_cost")) - 0.4) > 1e-12:
            cost_plan_errors += 1

    elapsed = time.perf_counter() - started
    total_errors = sum([
        mean_errors, stddev_errors, correlation_errors, probability_errors,
        deterministic_hash_errors, continuous_ledgers - invalid_correlation_rejections,
        information_value_errors, sequential_errors, information_hash_errors, cost_plan_errors,
    ])
    metrics = {
        "experiment": "E9 deterministic continuous approximation, correlated uncertainty, observation cost, information value and sequential decision",
        "seed": 20260723,
        "status": "PASS" if total_errors == 0 else "FAIL",
        "elapsed_seconds": elapsed,
        "continuous_correlated_uncertainty": {
            "ledgers": continuous_ledgers,
            "generated_branches": continuous_branches,
            "mean_errors": mean_errors,
            "standard_deviation_errors": stddev_errors,
            "correlation_errors": correlation_errors,
            "probability_mass_errors": probability_errors,
            "deterministic_hash_errors": deterministic_hash_errors,
            "invalid_correlation_rejections": invalid_correlation_rejections,
            "accuracy": 1.0 - (mean_errors + stddev_errors + correlation_errors + probability_errors) / max(1, continuous_ledgers * 6),
        },
        "information_value_and_sequential_decision": {
            "cases": sequential_cases,
            "one_step_information_value_errors": information_value_errors,
            "sequential_policy_errors": sequential_errors,
            "deterministic_hash_errors": information_hash_errors,
            "accuracy": 1.0 - (information_value_errors + sequential_errors) / max(1, sequential_cases * 3),
        },
        "cost_aware_observation": {
            "cases": cost_cases,
            "errors": cost_plan_errors,
            "minimum_cardinality_solution": ["z"],
            "minimum_cost_solution": ["x", "y"],
            "accuracy": 1.0 - cost_plan_errors / max(1, cost_cases * 2),
        },
        "scope_note": (
            "E9 validates deterministic finite approximations of declared continuous marginals and Gaussian-copula dependence, "
            "plus exact finite-horizon observe-then-act calculations over aligned supplied scenarios. It does not infer distributions, utilities or causal structure from external data."
        ),
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False, default=str))
    if total_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
