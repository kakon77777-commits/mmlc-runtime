from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from .errors import FDCSConfigurationError, InterventionError
from .persistence import semantic_hash
from .semantics import ledger_supports, semantic_profile
from .continuous import generate_continuous_ensemble_specs
from .types import MatrixLedger, MatrixRef, TemporalRef, TransactionResult, ValueRef
from .values import equivalent_value


SUPPORTED_INTERVENTIONS = {"do_set", "soft_shift", "soft_scale", "soft_affine"}


def _as_float(value: Any, *, name: str, minimum: float | None = None) -> float:
    try:
        number = float(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise FDCSConfigurationError(f"{name} must be numeric") from exc
    if minimum is not None and number < minimum:
        raise FDCSConfigurationError(f"{name} must be >= {minimum}")
    return number


def context_specs(ledger: MatrixLedger) -> list[dict[str, Any]]:
    """Return deterministic FDCS branch specifications."""
    config = dict(ledger.fdcs or {})
    if not bool(config.get("enabled", False)):
        return []
    raw_contexts = config.get("contexts", [])
    if raw_contexts is None:
        raw_contexts = []
    if not isinstance(raw_contexts, list):
        raise FDCSConfigurationError("fdcs.contexts must be an array")
    if (
        not raw_contexts
        and config.get("interventions")
        and ledger_supports(ledger, "0.6")
    ):
        raw_contexts = [{
            "id": str(config.get("intervention_context", "counterfactual")),
            "modulation": config.get("context_modulation", 1.0),
            "interventions": config.get("interventions", []),
        }]

    generated_contexts, _continuous_plan = generate_continuous_ensemble_specs(
        ledger_version=semantic_profile(ledger),
        continuous_config=dict(config.get("continuous_uncertainty", {})),
        transaction_ids=ledger.transactions,
    )
    raw_contexts = [*raw_contexts, *generated_contexts]

    seen: set[str] = set()
    base_context = str(config.get("base_context", config.get("context", "baseline")))
    specs: list[dict[str, Any]] = []
    for raw in raw_contexts:
        if not isinstance(raw, dict):
            raise FDCSConfigurationError("Each FDCS context must be an object")
        context_id = str(raw.get("id", "")).strip()
        if not context_id:
            raise FDCSConfigurationError("Each FDCS context requires a non-empty id")
        if context_id == base_context:
            raise FDCSConfigurationError(
                f"FDCS context id {context_id} conflicts with observational base_context"
            )
        if context_id in seen:
            raise FDCSConfigurationError(f"Duplicate FDCS context id: {context_id}")
        seen.add(context_id)
        interventions = raw.get("interventions", [])
        if not isinstance(interventions, list):
            raise FDCSConfigurationError(f"Context {context_id} interventions must be an array")
        audit = audit_intervention_set(ledger, interventions)
        if audit["status"] == "FAIL" and not ledger_supports(ledger, "0.7"):
            details = [item["error"] for item in audit["errors"]]
            details.extend(item["detail"] for item in audit["conflicts"])
            raise InterventionError("; ".join(details) or f"Context {context_id} intervention audit failed")
        probability = raw.get("probability")
        if probability is not None:
            probability = _as_float(
                probability,
                name=f"context {context_id} probability",
                minimum=0.0,
            )
        cost = _as_float(raw.get("cost", 0.0), name=f"context {context_id} cost", minimum=0.0)
        specs.append({
            "id": context_id,
            "modulation": _as_float(
                raw.get("modulation", 1.0),
                name=f"context {context_id} modulation",
                minimum=0.0,
            ),
            "interventions": deepcopy(interventions),
            "intervention_audit": audit,
            "probability": probability,
            "policy_id": str(raw.get("policy_id", "")).strip() or None,
            "scenario_id": str(raw.get("scenario_id", "")).strip() or context_id,
            "cost": cost,
            "metadata": deepcopy(dict(raw.get("metadata", {}))),
        })
    return specs


def _contains_ledger_reference(value: Any) -> bool:
    if isinstance(value, (ValueRef, MatrixRef, TemporalRef)):
        return True
    if isinstance(value, dict):
        return any(_contains_ledger_reference(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_ledger_reference(child) for child in value)
    return False


def _normalise_intervention(
    ledger: MatrixLedger,
    raw: dict[str, Any],
    position: int,
) -> dict[str, Any]:
    intervention_id = str(raw.get("id", f"intervention-{position}")).strip()
    if not intervention_id:
        raise InterventionError("Intervention id must be non-empty")
    kind = str(raw.get("kind", "do_set")).strip()
    if kind not in SUPPORTED_INTERVENTIONS:
        raise InterventionError(f"Unsupported intervention kind: {kind}")
    target = str(raw.get("target_tx_id", raw.get("target", ""))).strip()
    if not target or target not in ledger.transactions:
        raise InterventionError(f"Intervention {intervention_id} targets missing transaction: {target}")
    fixed_members = {member for group in ledger.fixed_point_groups for member in group.members}
    if target in fixed_members and not ledger_supports(ledger, "0.7"):
        raise InterventionError(
            f"Intervention {intervention_id} targets fixed-point member {target}; versions before 0.7 do not intervene inside fixed-point groups"
        )
    if kind != "do_set" and not ledger_supports(ledger, "0.7"):
        raise InterventionError(f"Soft interventions require MMLF v0.7: {intervention_id}")

    base = {
        "id": intervention_id,
        "kind": kind,
        "target_tx_id": target,
        "reason": str(raw.get("reason", "")),
        "metadata": deepcopy(dict(raw.get("metadata", {}))),
    }
    if kind == "do_set":
        if "value" not in raw:
            raise InterventionError(f"Intervention {intervention_id} requires value")
        if _contains_ledger_reference(raw["value"]):
            raise InterventionError(
                f"Intervention {intervention_id} value must be literal; ledger references would bypass the cut-edge contract"
            )
        return {**base, "value": raw["value"]}

    if kind == "soft_shift":
        shift = raw.get("shift", raw.get("value"))
        if shift is None:
            raise InterventionError(f"Intervention {intervention_id} requires shift or value")
        scale = 1
    elif kind == "soft_scale":
        scale = raw.get("scale", raw.get("value"))
        if scale is None:
            raise InterventionError(f"Intervention {intervention_id} requires scale or value")
        shift = 0
    else:
        scale = raw.get("scale", 1)
        shift = raw.get("shift", 0)
    if _contains_ledger_reference(scale) or _contains_ledger_reference(shift):
        raise InterventionError(
            f"Intervention {intervention_id} affine parameters must be literal"
        )
    try:
        # Validate arithmetic without coercing exact Fraction/SymPy values.
        _ = scale * 1 + shift
    except Exception as exc:
        raise InterventionError(
            f"Intervention {intervention_id} soft affine parameters must be numeric"
        ) from exc
    return {
        **base,
        "kind": "soft_affine",
        "declared_kind": kind,
        "scale": scale,
        "shift": shift,
    }


def audit_intervention_set(
    ledger: MatrixLedger,
    interventions: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Audit syntax, duplicate targets and semantic conflicts.

    This is a deterministic contract audit. It does not claim statistical
    identification from observational data.
    """
    normalised: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    redundancies: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for position, raw in enumerate(interventions):
        if not isinstance(raw, dict):
            errors.append({"position": position, "error": "Intervention must be an object"})
            continue
        try:
            item = _normalise_intervention(ledger, raw, position)
        except InterventionError as exc:
            errors.append({"position": position, "error": str(exc)})
            continue
        if item["id"] in seen_ids:
            errors.append({"position": position, "error": f"Duplicate intervention id: {item['id']}"})
            continue
        seen_ids.add(item["id"])
        normalised.append(item)

    by_target: dict[str, list[dict[str, Any]]] = {}
    for item in normalised:
        by_target.setdefault(item["target_tx_id"], []).append(item)
    executable: list[dict[str, Any]] = []
    for target, items in sorted(by_target.items()):
        if len(items) == 1:
            executable.append(items[0])
            continue
        first = items[0]
        all_equivalent = True
        for other in items[1:]:
            comparable_first = {k: v for k, v in first.items() if k not in {"id", "reason", "metadata", "declared_kind"}}
            comparable_other = {k: v for k, v in other.items() if k not in {"id", "reason", "metadata", "declared_kind"}}
            if comparable_first.keys() != comparable_other.keys():
                all_equivalent = False
                break
            for key in comparable_first:
                equal, _ = equivalent_value(comparable_first[key], comparable_other[key])
                if not equal:
                    all_equivalent = False
                    break
            if not all_equivalent:
                break
        if all_equivalent:
            redundancies.append({
                "target_tx_id": target,
                "intervention_ids": [item["id"] for item in items],
                "detail": "Equivalent interventions are redundant; the first declaration is executed",
            })
            executable.append(first)
        else:
            conflicts.append({
                "target_tx_id": target,
                "intervention_ids": [item["id"] for item in items],
                "kinds": [item["kind"] for item in items],
                "detail": "Multiple non-equivalent interventions target the same transaction without an explicit composition rule",
            })

    status = "FAIL" if errors or conflicts else ("WARN" if redundancies else "PASS")
    return {
        "status": status,
        "errors": errors,
        "conflicts": conflicts,
        "redundancies": redundancies,
        "normalised_interventions": normalised,
        "executable_interventions": executable,
        "target_count": len(by_target),
        "scope_note": "This audit detects declarative conflicts; it does not prove real-world causal identifiability.",
    }


def validate_interventions(
    ledger: MatrixLedger,
    interventions: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    audit = audit_intervention_set(ledger, interventions)
    if audit["status"] == "FAIL":
        details = [item["error"] for item in audit["errors"]]
        details.extend(item["detail"] for item in audit["conflicts"])
        raise InterventionError("; ".join(details) or "Intervention set failed validation")
    return {item["target_tx_id"]: item for item in audit["executable_interventions"]}


def apply_soft_intervention(value: Any, intervention: dict[str, Any]) -> Any:
    if intervention.get("kind") != "soft_affine":
        return value
    return intervention.get("scale", 1) * value + intervention.get("shift", 0)


def cut_incoming_edges(
    dependency_edges: dict[str, dict[str, set[str]]],
    intervention_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Cut incoming causal edges only for hard ``do_set`` interventions."""
    cuts: list[dict[str, Any]] = []
    for target in sorted(intervention_map):
        intervention = intervention_map[target]
        if intervention.get("kind") != "do_set":
            continue
        for source, channels in sorted(dependency_edges.get(target, {}).items()):
            cuts.append({
                "source": source,
                "target": target,
                "channels": sorted(channels),
                "intervention_id": intervention["id"],
            })
        dependency_edges[target] = {}
    return cuts


def _edge_weights(
    ledger: MatrixLedger,
    *,
    parent: str,
    child: str,
    context_modulation: float,
) -> dict[str, Any]:
    config = dict(ledger.fdcs or {})
    child_tx = ledger.transactions[child]
    parent_tx = ledger.transactions[parent]
    lag = max(0, int(child_tx.time_index) - int(parent_tx.time_index))
    decay = _as_float(config.get("decay_lambda", 1.0), name="fdcs.decay_lambda", minimum=0.0)
    fractal_decay = _as_float(
        config.get("fractal_decay_lambda", 1.0),
        name="fdcs.fractal_decay_lambda",
        minimum=0.0,
    )
    direction = dict(config.get("direction_weights", {}))
    global_forward = _as_float(direction.get("forward", 1.0), name="fdcs.direction_weights.forward", minimum=0.0)
    global_reverse = _as_float(direction.get("reverse", 1.0), name="fdcs.direction_weights.reverse", minimum=0.0)

    child_context = child_tx.context if isinstance(child_tx.context, dict) else {}
    parent_context = parent_tx.context if isinstance(parent_tx.context, dict) else {}
    base_weight = _as_float(child_context.get("causal_weight", 1.0), name=f"{child}.causal_weight")
    forward_factor = _as_float(
        child_context.get("causal_weight_forward", global_forward),
        name=f"{child}.causal_weight_forward",
        minimum=0.0,
    )
    reverse_factor = _as_float(
        child_context.get("causal_weight_reverse", global_reverse),
        name=f"{child}.causal_weight_reverse",
        minimum=0.0,
    )
    parent_level = int(parent_context.get("fractal_level", 0))
    child_level = int(child_context.get("fractal_level", 0))
    level_gap = abs(child_level - parent_level)
    temporal_factor = decay ** lag
    fractal_factor = fractal_decay ** level_gap
    common = base_weight * temporal_factor * fractal_factor * context_modulation
    return {
        "lag": lag,
        "base_weight": base_weight,
        "temporal_factor": temporal_factor,
        "parent_fractal_level": parent_level,
        "child_fractal_level": child_level,
        "fractal_level_gap": level_gap,
        "fractal_factor": fractal_factor,
        "context_modulation": context_modulation,
        "forward_factor": forward_factor,
        "reverse_factor": reverse_factor,
        "forward_effective_weight": common * forward_factor,
        "reverse_effective_weight": common * reverse_factor,
        "effective_weight": common * forward_factor,
    }


def build_fdcs_projection(
    ledger: MatrixLedger,
    results: dict[str, TransactionResult],
    dependency_edges: dict[str, dict[str, set[str]]],
    *,
    context_id: str | None = None,
    context_modulation: float | None = None,
    cut_edges: list[dict[str, Any]] | None = None,
    interventions: list[dict[str, Any]] | None = None,
    intervention_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = dict(ledger.fdcs or {})
    enabled = bool(config.get("enabled", False))
    if not enabled:
        return {"enabled": False, "status": "DISABLED", "nodes": [], "edges": [], "interventions": []}

    selected_context = str(context_id or config.get("context", "baseline"))
    modulation = _as_float(
        config.get("context_modulation", 1.0) if context_modulation is None else context_modulation,
        name=f"FDCS context {selected_context} modulation",
        minimum=0.0,
    )
    nodes: list[dict[str, Any]] = []
    for tx_id in sorted(results):
        tx = ledger.transactions[tx_id]
        tx_context = tx.context if isinstance(tx.context, dict) else {}
        result = results[tx_id]
        nodes.append({
            "node_id": tx_id,
            "series_id": tx.series_id or tx_id,
            "time_index": int(tx.time_index),
            "state": result.computed_result,
            "structural_state": result.structural_result,
            "status": result.status,
            "context": selected_context,
            "fractal_level": int(tx_context.get("fractal_level", 0)),
            "intervened": bool(result.intervened),
            "intervention_ids": list(result.intervention_ids),
            "intervention_kinds": list(result.intervention_kinds),
        })

    edges: list[dict[str, Any]] = []
    for child, parents in sorted(dependency_edges.items()):
        for parent, channels in sorted(parents.items()):
            weights = _edge_weights(
                ledger,
                parent=parent,
                child=child,
                context_modulation=modulation,
            )
            edges.append({
                "source": parent,
                "target": child,
                "channels": sorted(channels),
                "direction": "temporal" if weights["lag"] > 0 else "same_time",
                **weights,
            })

    intervention_records = []
    if interventions:
        for item in interventions:
            intervention_records.append({**deepcopy(dict(item)), "status": "EXECUTED"})
    elif config.get("interventions"):
        for item in config.get("interventions", []):
            intervention_records.append({**deepcopy(dict(item)), "status": "DECLARED_NOT_EXECUTED"})
    return {
        "enabled": True,
        "status": "PROJECTED",
        "context": selected_context,
        "decay_lambda": float(config.get("decay_lambda", 1.0)),
        "fractal_decay_lambda": float(config.get("fractal_decay_lambda", 1.0)),
        "context_modulation": modulation,
        "direction_weights": {
            "forward": float(dict(config.get("direction_weights", {})).get("forward", 1.0)),
            "reverse": float(dict(config.get("direction_weights", {})).get("reverse", 1.0)),
        },
        "nodes": nodes,
        "edges": edges,
        "cut_edges": deepcopy(cut_edges or []),
        "interventions": intervention_records,
        "intervention_audit": deepcopy(intervention_audit or {
            "status": "PASS", "errors": [], "conflicts": [], "redundancies": []
        }),
        "scope_note": (
            "v0.9 executes hard/soft counterfactual branches, re-solves declared fixed-point groups, audits discrete or deterministic continuous approximations, "
            "and exports deterministic branch differences. Reverse weights are audit/query traversal weights, not reverse causation."
        ),
    }


def _delta(before: Any, after: Any) -> Any:
    try:
        return after - before
    except Exception:
        return {"before": before, "after": after}


def build_branch_diff_ledger(
    *,
    context_id: str,
    run: Any,
    baseline_results: dict[str, TransactionResult],
) -> dict[str, Any]:
    previous_hash = "0" * 64
    records: list[dict[str, Any]] = []
    for index, tx_id in enumerate(sorted(run.transactions)):
        baseline = baseline_results[tx_id]
        branch = run.transactions[tx_id]
        equivalent, _ = equivalent_value(baseline.computed_result, branch.computed_result)
        if branch.intervened:
            role = "hard_intervention" if "do_set" in branch.intervention_kinds else "soft_intervention"
        elif not equivalent and branch.fixed_point_group:
            role = "fixed_point_response"
        elif not equivalent:
            role = "descendant_response"
        else:
            role = "unchanged"
        payload = {
            "index": index,
            "context_id": context_id,
            "tx_id": tx_id,
            "baseline_value": baseline.computed_result,
            "branch_value": branch.computed_result,
            "delta": _delta(baseline.computed_result, branch.computed_result) if not equivalent else 0,
            "changed": not equivalent,
            "change_role": role,
            "baseline_status": baseline.status,
            "branch_status": branch.status,
            "intervention_ids": list(branch.intervention_ids),
            "intervention_kinds": list(branch.intervention_kinds),
            "fixed_point_group": branch.fixed_point_group,
        }
        entry_hash = semantic_hash({"previous_hash": previous_hash, "record": payload})
        record = {**payload, "previous_hash": previous_hash, "entry_hash": entry_hash}
        records.append(record)
        previous_hash = entry_hash
    changed_records = [record for record in records if record["changed"]]
    return {
        "format": "MMLC-BRANCH-DIFF",
        "version": "0.9",
        "context_id": context_id,
        "record_count": len(records),
        "changed_count": len(changed_records),
        "records": records,
        "head_hash": previous_hash,
        "append_only_order": "transaction_id_lexicographic",
    }


def branch_summary(
    *,
    context_id: str,
    modulation: float,
    run: Any,
    baseline_results: dict[str, TransactionResult],
    intervention_audit: dict[str, Any] | None = None,
    probability: float | None = None,
    policy_id: str | None = None,
    scenario_id: str | None = None,
    cost: float = 0.0,
) -> dict[str, Any]:
    diff = build_branch_diff_ledger(
        context_id=context_id,
        run=run,
        baseline_results=baseline_results,
    )
    changed = [record["tx_id"] for record in diff["records"] if record["changed"]]
    deltas = {record["tx_id"]: record["delta"] for record in diff["records"] if record["changed"]}
    projection = run.fdcs_projection
    return {
        "context_id": context_id,
        "status": "EXECUTED",
        "global_audit": run.global_audit.get("status"),
        "semantic_hash": run.semantic_hash,
        "execution_hash": run.execution_hash,
        "context_modulation": modulation,
        "probability": probability,
        "policy_id": policy_id,
        "scenario_id": scenario_id or context_id,
        "cost": cost,
        "interventions": deepcopy(projection.get("interventions", [])),
        "intervention_audit": deepcopy(intervention_audit or projection.get("intervention_audit", {})),
        "cut_edges": deepcopy(projection.get("cut_edges", [])),
        "changed_transactions": changed,
        "deltas": deltas,
        "differential_ledger": diff,
        "values": {tx_id: run.transactions[tx_id].computed_result for tx_id in sorted(run.transactions)},
        "projection": projection,
        "fixed_point_analysis": deepcopy(run.fixed_point_analysis),
        "counterfactual_declared_results_ignored": True,
    }


def build_identifiability_audit(
    *,
    contexts: dict[str, dict[str, Any]],
    base_context: str,
    observed_transactions: Iterable[str],
) -> dict[str, Any]:
    observed = sorted(set(str(tx_id) for tx_id in observed_transactions))
    executable = {
        context_id: item
        for context_id, item in contexts.items()
        if item.get("status") in {"OBSERVED", "EXECUTED"}
    }
    signatures: dict[str, str] = {}
    for context_id, item in executable.items():
        values = item.get("values", {})
        signatures[context_id] = semantic_hash({tx_id: values.get(tx_id) for tx_id in observed})
    classes_by_hash: dict[str, list[str]] = {}
    for context_id, signature in signatures.items():
        classes_by_hash.setdefault(signature, []).append(context_id)
    equivalence_classes = [sorted(group) for group in classes_by_hash.values()]
    equivalence_classes.sort(key=lambda group: group[0])
    base_signature = signatures.get(base_context)
    context_results: dict[str, Any] = {}
    for context_id in sorted(contexts):
        item = contexts[context_id]
        if item.get("status") == "CONFLICT":
            context_results[context_id] = {
                "status": "CONFLICT",
                "ledger_distinguishable_from_baseline": False,
                "pairwise_unique": False,
                "indistinguishable_with": [],
            }
            continue
        signature = signatures.get(context_id)
        same_class = next((group for group in equivalence_classes if context_id in group), [context_id])
        visible = context_id != base_context and (base_signature is not None and signature != base_signature)
        pairwise_unique = len(same_class) == 1
        status = "BASELINE" if context_id == base_context else (
            "DISTINGUISHABLE" if visible else "NOT_DISTINGUISHABLE"
        )
        if context_id != base_context and visible and not pairwise_unique:
            status = "EFFECT_VISIBLE_CONTEXT_NOT_UNIQUE"
        context_results[context_id] = {
            "status": status,
            "signature": signature,
            "ledger_distinguishable_from_baseline": bool(visible),
            "pairwise_unique": pairwise_unique,
            "indistinguishable_with": [x for x in same_class if x != context_id],
        }
    counterfactual_ids = [context_id for context_id in contexts if context_id != base_context]
    return {
        "status": "AUDITED",
        "observed_transactions": observed,
        "context_results": context_results,
        "equivalence_classes": equivalence_classes,
        "all_effects_visible": all(
            context_results[context_id].get("ledger_distinguishable_from_baseline", False)
            for context_id in counterfactual_ids
            if context_results[context_id].get("status") != "CONFLICT"
        ),
        "all_contexts_pairwise_distinguishable": all(len(group) == 1 for group in equivalence_classes),
        "scope_note": (
            "Ledger identifiability means deterministic distinguishability on the declared observed transactions under the supplied model. "
            "It is not statistical causal identification from observational data."
        ),
    }
