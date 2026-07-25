from __future__ import annotations

import itertools
import math
from copy import deepcopy
from typing import Any, Iterable

from .persistence import semantic_hash
from .values import is_numeric, serialize_value


def _finite_nonnegative(value: Any, *, name: str) -> float:
    try:
        number = float(value)
    except Exception as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return number


def _outcome_key(value: Any) -> str:
    return semantic_hash({"value": serialize_value(value)})


def _distribution(values: list[tuple[str, float, Any]]) -> dict[str, Any]:
    support: dict[str, dict[str, Any]] = {}
    numeric = True
    for context_id, probability, value in values:
        key = _outcome_key(value)
        entry = support.setdefault(key, {
            "value": value,
            "probability": 0.0,
            "contexts": [],
        })
        entry["probability"] += probability
        entry["contexts"].append(context_id)
        numeric = numeric and is_numeric(value)
    entries = sorted(support.values(), key=lambda item: semantic_hash(serialize_value(item["value"])))
    entropy = -sum(
        item["probability"] * math.log2(item["probability"])
        for item in entries if item["probability"] > 0
    )
    result: dict[str, Any] = {
        "support_size": len(entries),
        "support": entries,
        "entropy_bits": entropy,
        "deterministic": len(entries) == 1,
        "numeric": numeric,
    }
    if numeric:
        floats = [(probability, float(value)) for _, probability, value in values]
        mean = sum(probability * value for probability, value in floats)
        variance = sum(probability * (value - mean) ** 2 for probability, value in floats)
        result.update({
            "expected_value": mean,
            "variance": variance,
            "standard_deviation": math.sqrt(max(0.0, variance)),
            "minimum": min(value for _, value in floats),
            "maximum": max(value for _, value in floats),
        })
    else:
        result.update({
            "expected_value": None,
            "variance": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
        })
    return result


def build_probability_analysis(
    *,
    contexts: dict[str, dict[str, Any]],
    context_specs: Iterable[dict[str, Any]],
    tolerance: float = 1.0e-12,
) -> dict[str, Any]:
    specs = [deepcopy(dict(spec)) for spec in context_specs]
    probabilistic = [spec for spec in specs if spec.get("probability") is not None]
    if not probabilistic:
        return {
            "enabled": False,
            "status": "DISABLED",
            "groups": {},
            "scope_note": "No declared branch probabilities.",
        }

    groups: dict[str, list[dict[str, Any]]] = {}
    for spec in probabilistic:
        group_id = str(spec.get("policy_id") or "ensemble")
        groups.setdefault(group_id, []).append(spec)

    output_groups: dict[str, Any] = {}
    overall_status = "PASS"
    for group_id, group_specs in sorted(groups.items()):
        errors: list[str] = []
        weighted_contexts: list[dict[str, Any]] = []
        total = 0.0
        for spec in sorted(group_specs, key=lambda item: str(item["id"])):
            try:
                probability = _finite_nonnegative(
                    spec.get("probability"), name=f"context {spec['id']} probability"
                )
            except ValueError as exc:
                errors.append(str(exc))
                continue
            total += probability
            context = contexts.get(str(spec["id"]), {})
            status = context.get("status")
            if probability > tolerance and status != "EXECUTED":
                errors.append(
                    f"Context {spec['id']} has positive probability {probability} but status is {status or 'MISSING'}"
                )
            weighted_contexts.append({
                "context_id": str(spec["id"]),
                "scenario_id": str(spec.get("scenario_id") or spec["id"]),
                "probability": probability,
                "cost": float(spec.get("cost", 0.0)),
                "status": status,
            })
        if abs(total - 1.0) > tolerance:
            errors.append(f"Probability mass for group {group_id} is {total}, expected 1.0")

        transaction_uncertainty: dict[str, Any] = {}
        if not errors:
            executable_ids = [item["context_id"] for item in weighted_contexts]
            tx_ids = sorted(set.intersection(*[
                set(contexts[context_id].get("values", {})) for context_id in executable_ids
            ])) if executable_ids else []
            probability_by_context = {item["context_id"]: item["probability"] for item in weighted_contexts}
            for tx_id in tx_ids:
                transaction_uncertainty[tx_id] = _distribution([
                    (context_id, probability_by_context[context_id], contexts[context_id]["values"][tx_id])
                    for context_id in executable_ids
                ])

        status = "FAIL" if errors else "PASS"
        if status == "FAIL":
            overall_status = "FAIL"
        payload = {
            "group_id": group_id,
            "status": status,
            "probability_sum": total,
            "contexts": weighted_contexts,
            "errors": errors,
            "transaction_uncertainty": transaction_uncertainty,
        }
        payload["analysis_hash"] = semantic_hash(payload)
        output_groups[group_id] = payload

    result = {
        "enabled": True,
        "status": overall_status,
        "groups": output_groups,
        "scope_note": (
            "Probabilities are declared weights over supplied deterministic model branches. "
            "They are not learned frequencies or guarantees about the external world."
        ),
    }
    result["analysis_hash"] = semantic_hash(result)
    return result


def build_policy_analysis(
    *,
    contexts: dict[str, dict[str, Any]],
    context_specs: Iterable[dict[str, Any]],
    probability_analysis: dict[str, Any],
    policy_config: dict[str, Any] | None,
) -> dict[str, Any]:
    config = dict(policy_config or {})
    if not bool(config.get("enabled", False)):
        return {"enabled": False, "status": "DISABLED", "policies": {}}
    objectives = list(config.get("objectives", []))
    if not objectives:
        return {
            "enabled": True,
            "status": "FAIL",
            "errors": ["policy_selection.objectives must contain at least one objective"],
            "policies": {},
        }
    risk_aversion = _finite_nonnegative(config.get("risk_aversion", 0.0), name="risk_aversion")
    cost_weight = _finite_nonnegative(config.get("cost_weight", 1.0), name="cost_weight")
    tolerance = float(config.get("tie_tolerance", 1.0e-12))
    specs_by_id = {str(spec["id"]): dict(spec) for spec in context_specs}

    policies: dict[str, Any] = {}
    errors: list[str] = []
    for policy_id, group in sorted(probability_analysis.get("groups", {}).items()):
        if policy_id == "ensemble":
            continue
        if group.get("status") != "PASS":
            policies[policy_id] = {"status": "FAIL", "errors": list(group.get("errors", []))}
            continue
        utilities: list[tuple[float, float]] = []
        expected_cost = 0.0
        scenario_rows: list[dict[str, Any]] = []
        policy_errors: list[str] = []
        for item in group.get("contexts", []):
            context_id = item["context_id"]
            probability = float(item["probability"])
            values = contexts[context_id].get("values", {})
            utility = 0.0
            contributions: list[dict[str, Any]] = []
            for objective in objectives:
                tx_id = str(objective.get("tx_id", ""))
                direction = str(objective.get("direction", "maximize"))
                weight = float(objective.get("weight", 1.0))
                if tx_id not in values or not is_numeric(values[tx_id]):
                    policy_errors.append(f"Context {context_id} objective {tx_id} is missing or non-numeric")
                    continue
                sign = 1.0 if direction == "maximize" else -1.0 if direction == "minimize" else None
                if sign is None:
                    policy_errors.append(f"Unsupported objective direction: {direction}")
                    continue
                contribution = sign * weight * float(values[tx_id])
                utility += contribution
                contributions.append({
                    "tx_id": tx_id,
                    "direction": direction,
                    "weight": weight,
                    "value": values[tx_id],
                    "contribution": contribution,
                })
            spec = specs_by_id.get(context_id, {})
            cost = float(spec.get("cost", item.get("cost", 0.0)))
            expected_cost += probability * cost
            utilities.append((probability, utility))
            scenario_rows.append({
                "context_id": context_id,
                "scenario_id": spec.get("scenario_id", context_id),
                "probability": probability,
                "utility": utility,
                "cost": cost,
                "objective_contributions": contributions,
            })
        if policy_errors:
            policies[policy_id] = {"status": "FAIL", "errors": sorted(set(policy_errors)), "scenarios": scenario_rows}
            errors.extend(policy_errors)
            continue
        expected_utility = sum(probability * utility for probability, utility in utilities)
        variance = sum(probability * (utility - expected_utility) ** 2 for probability, utility in utilities)
        stddev = math.sqrt(max(0.0, variance))
        score = expected_utility - risk_aversion * stddev - cost_weight * expected_cost
        policies[policy_id] = {
            "status": "PASS",
            "expected_utility": expected_utility,
            "utility_variance": variance,
            "utility_standard_deviation": stddev,
            "expected_cost": expected_cost,
            "risk_penalty": risk_aversion * stddev,
            "cost_penalty": cost_weight * expected_cost,
            "score": score,
            "scenarios": scenario_rows,
        }

    valid = {policy_id: item for policy_id, item in policies.items() if item.get("status") == "PASS"}
    selected: list[str] = []
    best_score: float | None = None
    if valid:
        best_score = max(float(item["score"]) for item in valid.values())
        selected = sorted(
            policy_id for policy_id, item in valid.items()
            if abs(float(item["score"]) - best_score) <= tolerance
        )
    status = "PASS" if valid and not errors else ("PARTIAL" if valid else "FAIL")
    result = {
        "enabled": True,
        "status": status,
        "risk_aversion": risk_aversion,
        "cost_weight": cost_weight,
        "objectives": deepcopy(objectives),
        "policies": policies,
        "selected_policies": selected,
        "best_score": best_score,
        "errors": sorted(set(errors)),
        "scope_note": (
            "Policy ranking is conditional on declared branch probabilities, objective weights, costs and the supplied structural model. "
            "It is not a normative recommendation outside those assumptions."
        ),
    }
    result["analysis_hash"] = semantic_hash(result)
    return result


def build_observation_plan(
    *,
    contexts: dict[str, dict[str, Any]],
    base_context: str,
    observed_transactions: Iterable[str],
    config: dict[str, Any] | None,
    all_transactions: Iterable[str],
) -> dict[str, Any]:
    cfg = dict(config or {})
    if not bool(cfg.get("enabled", False)):
        return {"enabled": False, "status": "DISABLED"}
    observed = sorted(set(str(x) for x in observed_transactions))
    executable = {
        context_id: item for context_id, item in contexts.items()
        if item.get("status") in {"OBSERVED", "EXECUTED"}
    }
    context_ids = sorted(executable)
    if len(context_ids) <= 1:
        return {
            "enabled": True, "status": "ALREADY_DISTINGUISHABLE", "minimum_size": 0,
            "solutions": [[]], "observed_transactions": observed, "ambiguous_pairs": [],
        }

    def signature(context_id: str, txs: Iterable[str]) -> str:
        values = executable[context_id].get("values", {})
        return semantic_hash({tx_id: serialize_value(values.get(tx_id)) for tx_id in sorted(txs)})

    ambiguous_pairs = [
        (left, right)
        for left, right in itertools.combinations(context_ids, 2)
        if signature(left, observed) == signature(right, observed)
    ]
    if not ambiguous_pairs:
        return {
            "enabled": True, "status": "ALREADY_DISTINGUISHABLE", "minimum_size": 0,
            "solutions": [[]], "observed_transactions": observed, "ambiguous_pairs": [],
            "scope_note": "All executable model branches are already distinct on the declared observations.",
        }

    raw_candidates = cfg.get("candidate_transactions")
    candidates = sorted(set(str(x) for x in (raw_candidates if raw_candidates is not None else all_transactions)) - set(observed))
    raw_costs = dict(cfg.get("observation_costs", {}))
    observation_costs: dict[str, float] = {}
    for tx_id in candidates:
        observation_costs[tx_id] = _finite_nonnegative(
            raw_costs.get(tx_id, 1.0), name=f"observation cost for {tx_id}"
        )
    max_candidates = int(cfg.get("max_candidates", 24))
    max_size = int(cfg.get("max_additional_observations", min(4, len(candidates))))
    max_solutions = int(cfg.get("max_solutions", 32))
    if len(candidates) > max_candidates:
        return {
            "enabled": True,
            "status": "SEARCH_LIMIT",
            "minimum_size": None,
            "solutions": [],
            "observed_transactions": observed,
            "candidate_count": len(candidates),
            "max_candidates": max_candidates,
            "ambiguous_pairs": [list(pair) for pair in ambiguous_pairs],
            "observation_costs": observation_costs,
            "scope_note": "Exact observation planning was not run because the declared candidate set exceeds the configured limit.",
        }

    pair_distinguishers: dict[tuple[str, str], set[str]] = {}
    impossible_pairs: list[list[str]] = []
    for pair in ambiguous_pairs:
        left, right = pair
        distinguishers = {
            tx_id for tx_id in candidates
            if signature(left, [tx_id]) != signature(right, [tx_id])
        }
        pair_distinguishers[pair] = distinguishers
        if not distinguishers:
            impossible_pairs.append([left, right])
    if impossible_pairs:
        return {
            "enabled": True,
            "status": "IMPOSSIBLE",
            "minimum_size": None,
            "solutions": [],
            "observed_transactions": observed,
            "candidate_transactions": candidates,
            "ambiguous_pairs": [list(pair) for pair in ambiguous_pairs],
            "impossible_pairs": impossible_pairs,
            "observation_costs": observation_costs,
            "scope_note": "At least one pair of supplied model branches has identical values on every candidate transaction.",
        }

    solutions: list[list[str]] = []
    all_feasible: list[tuple[float, int, list[str]]] = []
    searched = 0
    for size in range(1, min(max_size, len(candidates)) + 1):
        for combo in itertools.combinations(candidates, size):
            searched += 1
            selected = set(combo)
            if all(selected & pair_distinguishers[pair] for pair in ambiguous_pairs):
                combo_list = list(combo)
                total_cost = sum(observation_costs[tx_id] for tx_id in combo_list)
                all_feasible.append((total_cost, size, combo_list))
                if not solutions or size == len(solutions[0]):
                    if len(solutions) < max_solutions:
                        solutions.append(combo_list)
        # Keep searching larger supports for a potentially cheaper cost solution.
    status = "FOUND" if solutions else "NOT_FOUND_WITHIN_LIMIT"
    minimum_cost: float | None = None
    minimum_cost_solutions: list[list[str]] = []
    if all_feasible:
        minimum_cost = min(item[0] for item in all_feasible)
        minimum_cost_size = min(item[1] for item in all_feasible if abs(item[0] - minimum_cost) <= 1.0e-12)
        minimum_cost_solutions = [
            item[2] for item in all_feasible
            if abs(item[0] - minimum_cost) <= 1.0e-12 and item[1] == minimum_cost_size
        ][:max_solutions]
    result = {
        "enabled": True,
        "status": status,
        "minimum_size": len(solutions[0]) if solutions else None,
        "solutions": solutions,
        "minimum_cost": minimum_cost,
        "minimum_cost_solutions": minimum_cost_solutions,
        "observation_costs": observation_costs,
        "observed_transactions": observed,
        "candidate_transactions": candidates,
        "ambiguous_pairs": [list(pair) for pair in ambiguous_pairs],
        "searched_candidate_sets": searched,
        "max_additional_observations": max_size,
        "base_context": base_context,
        "scope_note": (
            "This is an exact finite hitting-set search over supplied model branch values. "
            "It reports both minimum-cardinality and minimum-declared-cost solutions; neither establishes universal causal sufficiency."
        ),
    }
    result["analysis_hash"] = semantic_hash(result)
    return result


def _policy_objective_utility(
    values: dict[str, Any],
    objectives: list[dict[str, Any]],
) -> tuple[float | None, list[dict[str, Any]], list[str]]:
    utility = 0.0
    contributions: list[dict[str, Any]] = []
    errors: list[str] = []
    for objective in objectives:
        tx_id = str(objective.get("tx_id", ""))
        direction = str(objective.get("direction", "maximize"))
        weight = float(objective.get("weight", 1.0))
        if tx_id not in values or not is_numeric(values[tx_id]):
            errors.append(f"objective {tx_id} is missing or non-numeric")
            continue
        if direction == "maximize":
            sign = 1.0
        elif direction == "minimize":
            sign = -1.0
        else:
            errors.append(f"unsupported objective direction: {direction}")
            continue
        contribution = sign * weight * float(values[tx_id])
        utility += contribution
        contributions.append({
            "tx_id": tx_id,
            "direction": direction,
            "weight": weight,
            "value": values[tx_id],
            "contribution": contribution,
        })
    return (None if errors else utility), contributions, errors


def build_information_value_analysis(
    *,
    contexts: dict[str, dict[str, Any]],
    context_specs: Iterable[dict[str, Any]],
    probability_analysis: dict[str, Any],
    policy_config: dict[str, Any] | None,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    cfg = deepcopy(dict(config or {}))
    if not bool(cfg.get("enabled", False)):
        return {"enabled": False, "status": "DISABLED"}
    policy_cfg = dict(policy_config or {})
    objectives = list(cfg.get("objectives", policy_cfg.get("objectives", [])))
    if not objectives:
        return {"enabled": True, "status": "FAIL", "errors": ["information_value requires objectives"]}
    cost_weight = _finite_nonnegative(
        cfg.get("policy_cost_weight", policy_cfg.get("cost_weight", 1.0)),
        name="information_value policy_cost_weight",
    )
    tolerance = float(cfg.get("tolerance", 1.0e-12))
    horizon = int(cfg.get("horizon", 1))
    if horizon < 0 or horizon > int(cfg.get("max_horizon", 3)):
        return {"enabled": True, "status": "FAIL", "errors": ["information_value horizon outside configured limit"]}
    candidates = sorted(set(str(x) for x in cfg.get("candidate_transactions", [])))
    if not candidates:
        return {"enabled": True, "status": "FAIL", "errors": ["information_value requires candidate_transactions"]}
    max_candidates = int(cfg.get("max_candidates", 12))
    if len(candidates) > max_candidates:
        return {
            "enabled": True, "status": "SEARCH_LIMIT", "candidate_count": len(candidates),
            "max_candidates": max_candidates,
        }
    costs = {
        tx_id: _finite_nonnegative(dict(cfg.get("observation_costs", {})).get(tx_id, 0.0), name=f"observation cost for {tx_id}")
        for tx_id in candidates
    }
    specs_by_id = {str(spec["id"]): dict(spec) for spec in context_specs}
    groups = {
        policy_id: group for policy_id, group in probability_analysis.get("groups", {}).items()
        if policy_id != "ensemble" and group.get("status") == "PASS"
    }
    if len(groups) < 2:
        return {
            "enabled": True, "status": "FAIL",
            "errors": ["information_value requires at least two valid policy groups"],
        }

    policy_scenarios: dict[str, dict[str, dict[str, Any]]] = {}
    errors: list[str] = []
    for policy_id, group in sorted(groups.items()):
        rows: dict[str, dict[str, Any]] = {}
        for item in group.get("contexts", []):
            context_id = str(item["context_id"])
            scenario_id = str(item["scenario_id"])
            spec = specs_by_id.get(context_id, {})
            values = contexts.get(context_id, {}).get("values", {})
            utility, contributions, objective_errors = _policy_objective_utility(values, objectives)
            if objective_errors:
                errors.extend(f"{context_id}: {error}" for error in objective_errors)
                continue
            net_utility = float(utility) - cost_weight * float(spec.get("cost", item.get("cost", 0.0)))
            rows[scenario_id] = {
                "context_id": context_id,
                "probability": float(item["probability"]),
                "utility": float(utility),
                "net_utility": net_utility,
                "values": values,
                "contributions": contributions,
            }
        policy_scenarios[policy_id] = rows
    if errors:
        return {"enabled": True, "status": "FAIL", "errors": sorted(set(errors))}

    policy_ids = sorted(policy_scenarios)
    scenario_sets = [set(policy_scenarios[policy_id]) for policy_id in policy_ids]
    scenario_ids = sorted(set.intersection(*scenario_sets)) if scenario_sets else []
    if not scenario_ids or any(set(rows) != set(scenario_ids) for rows in policy_scenarios.values()):
        return {
            "enabled": True, "status": "FAIL",
            "errors": ["All policies must contain the same scenario_id set for adaptive information-value analysis"],
        }
    reference = policy_scenarios[policy_ids[0]]
    probabilities = {scenario_id: reference[scenario_id]["probability"] for scenario_id in scenario_ids}
    if abs(sum(probabilities.values()) - 1.0) > tolerance:
        return {"enabled": True, "status": "FAIL", "errors": ["Aligned scenario probabilities must sum to 1"]}
    for policy_id in policy_ids[1:]:
        for scenario_id in scenario_ids:
            other = policy_scenarios[policy_id][scenario_id]["probability"]
            if abs(other - probabilities[scenario_id]) > tolerance:
                errors.append(f"Scenario probability mismatch for {scenario_id} across policies")
    if errors:
        return {"enabled": True, "status": "FAIL", "errors": sorted(set(errors))}

    signal_keys: dict[str, dict[str, str]] = {}
    signal_values: dict[str, dict[str, Any]] = {}
    invalid_candidates: dict[str, str] = {}
    for candidate in candidates:
        keys: dict[str, str] = {}
        values_out: dict[str, Any] = {}
        for scenario_id in scenario_ids:
            policy_values = []
            for policy_id in policy_ids:
                values = policy_scenarios[policy_id][scenario_id]["values"]
                if candidate not in values:
                    invalid_candidates[candidate] = f"candidate {candidate} missing in policy {policy_id}, scenario {scenario_id}"
                    break
                policy_values.append(values[candidate])
            if candidate in invalid_candidates:
                break
            hashes = {semantic_hash({"value": serialize_value(value)}) for value in policy_values}
            if len(hashes) != 1:
                invalid_candidates[candidate] = (
                    f"candidate {candidate} is policy-dependent in scenario {scenario_id}; "
                    "pre-decision observations must be policy-invariant"
                )
                break
            values_out[scenario_id] = policy_values[0]
            keys[scenario_id] = next(iter(hashes))
        if candidate not in invalid_candidates:
            signal_keys[candidate] = keys
            signal_values[candidate] = values_out
    valid_candidates = sorted(signal_keys)
    if not valid_candidates:
        return {
            "enabled": True, "status": "FAIL", "errors": sorted(invalid_candidates.values()),
            "invalid_candidates": invalid_candidates,
        }

    def conditional_policy_values(subset: tuple[str, ...]) -> tuple[dict[str, float], float, list[str]]:
        mass = sum(probabilities[scenario_id] for scenario_id in subset)
        values_by_policy = {
            policy_id: sum(
                probabilities[scenario_id] * policy_scenarios[policy_id][scenario_id]["net_utility"]
                for scenario_id in subset
            ) / mass
            for policy_id in policy_ids
        }
        best = max(values_by_policy.values())
        selected = sorted(policy_id for policy_id, value in values_by_policy.items() if abs(value - best) <= tolerance)
        return values_by_policy, best, selected

    all_scenarios = tuple(scenario_ids)
    prior_values, prior_best, prior_selected = conditional_policy_values(all_scenarios)

    one_step: dict[str, Any] = {}
    for candidate in valid_candidates:
        partitions: dict[str, list[str]] = {}
        for scenario_id in scenario_ids:
            partitions.setdefault(signal_keys[candidate][scenario_id], []).append(scenario_id)
        after_value = 0.0
        rules: list[dict[str, Any]] = []
        for key, subset_list in sorted(partitions.items()):
            subset = tuple(sorted(subset_list))
            mass = sum(probabilities[scenario_id] for scenario_id in subset)
            conditional_mass = mass
            values_by_policy, best, selected = conditional_policy_values(subset)
            after_value += conditional_mass * best
            representative = signal_values[candidate][subset[0]]
            rules.append({
                "observation_value": representative,
                "scenario_ids": list(subset),
                "probability": conditional_mass,
                "policy_values": values_by_policy,
                "selected_policies": selected,
                "conditional_value": best,
            })
        gross = after_value - prior_best
        net = gross - costs[candidate]
        one_step[candidate] = {
            "candidate": candidate,
            "observation_cost": costs[candidate],
            "gross_information_value": gross,
            "net_information_value": net,
            "expected_value_after_observation": after_value,
            "decision_rules": rules,
            "uninformative": len(partitions) == 1,
        }

    memo: dict[tuple[tuple[str, ...], tuple[str, ...], int], tuple[float, dict[str, Any]]] = {}

    def solve(subset: tuple[str, ...], available: tuple[str, ...], depth: int) -> tuple[float, dict[str, Any]]:
        key = (subset, available, depth)
        if key in memo:
            return memo[key]
        values_by_policy, stop_value, selected = conditional_policy_values(subset)
        best_value = stop_value
        best_action: dict[str, Any] = {
            "action": "choose_policy",
            "selected_policies": selected,
            "policy_values": values_by_policy,
            "expected_value": stop_value,
            "scenario_ids": list(subset),
        }
        if depth > 0:
            subset_mass = sum(probabilities[scenario_id] for scenario_id in subset)
            for candidate in available:
                partitions: dict[str, list[str]] = {}
                for scenario_id in subset:
                    partitions.setdefault(signal_keys[candidate][scenario_id], []).append(scenario_id)
                if len(partitions) <= 1:
                    continue
                expected = -costs[candidate]
                branches: list[dict[str, Any]] = []
                remaining = tuple(item for item in available if item != candidate)
                for signal_key, child_list in sorted(partitions.items()):
                    child = tuple(sorted(child_list))
                    child_mass = sum(probabilities[scenario_id] for scenario_id in child)
                    conditional_probability = child_mass / subset_mass
                    child_value, child_tree = solve(child, remaining, depth - 1)
                    expected += conditional_probability * child_value
                    branches.append({
                        "observation_value": signal_values[candidate][child[0]],
                        "conditional_probability": conditional_probability,
                        "scenario_ids": list(child),
                        "next": child_tree,
                    })
                if expected > best_value + tolerance or (
                    abs(expected - best_value) <= tolerance
                    and best_action.get("action") == "observe"
                    and candidate < str(best_action.get("transaction"))
                ):
                    best_value = expected
                    best_action = {
                        "action": "observe",
                        "transaction": candidate,
                        "observation_cost": costs[candidate],
                        "expected_value": expected,
                        "scenario_ids": list(subset),
                        "branches": branches,
                    }
        memo[key] = (best_value, best_action)
        return memo[key]

    sequential_value, decision_tree = solve(all_scenarios, tuple(valid_candidates), horizon)
    if one_step:
        best_one_step_value = max(row["net_information_value"] for row in one_step.values())
        selected_one_step = sorted(
            candidate for candidate, item in one_step.items()
            if abs(item["net_information_value"] - best_one_step_value) <= tolerance
        )
    else:
        selected_one_step = []
    result = {
        "enabled": True,
        "status": "PASS",
        "policy_ids": policy_ids,
        "scenario_ids": scenario_ids,
        "scenario_probabilities": probabilities,
        "objectives": objectives,
        "policy_cost_weight": cost_weight,
        "prior_policy_values": prior_values,
        "prior_best_value": prior_best,
        "prior_selected_policies": prior_selected,
        "candidate_information_values": one_step,
        "best_one_step_candidates": selected_one_step,
        "horizon": horizon,
        "sequential_expected_value": sequential_value,
        "sequential_net_information_value": sequential_value - prior_best,
        "decision_tree": decision_tree,
        "observation_costs": costs,
        "invalid_candidates": invalid_candidates,
        "scope_note": (
            "This is an exact finite-horizon observe-then-act calculation over declared aligned scenarios. "
            "It uses risk-neutral expected net utility for adaptive decisions and does not learn probabilities or causal structure from data."
        ),
    }
    result["analysis_hash"] = semantic_hash(result)
    return result
