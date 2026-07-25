from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .version import __version__
from .audit import (
    aggregate_audits,
    dependency_declaration_check,
    dependency_health_check,
    source_check,
    value_check,
)
from .constraints import detect_cross_axis_conflicts, evaluate_constraints, find_minimum_repair_sets
from .corrections import apply_corrections
from .dependency import (
    build_dependency_edges,
    resolve_matrix_target,
    resolve_temporal_target,
    temporal_index,
)
from .errors import MMLCError, TraversalSemanticError
from .fdcs import (
    apply_soft_intervention,
    audit_intervention_set,
    branch_summary,
    build_fdcs_projection,
    build_identifiability_audit,
    context_specs,
    cut_incoming_edges,
    validate_interventions,
)
from .fixed_point import convergence_delta, execution_units
from .layout import PHYSICAL_TRAVERSALS, physical_sequence
from .operators import OperatorRegistry, build_default_registry
from .persistence import semantic_hash
from .semantics import semantic_profile
from .root_cause import build_root_cause_analysis
from .temporal import build_temporal_analysis
from .traversal import traverse
from .uncertainty import (
    build_information_value_analysis, build_observation_plan, build_policy_analysis,
    build_probability_analysis,
)
from .continuous import build_continuous_approximation_analysis, generate_continuous_ensemble_specs
from .values import equivalent_value
from .types import (
    CheckResult,
    FixedPointGroup,
    MatrixLedger,
    MatrixRef,
    RunResult,
    TemporalRef,
    TransactionResult,
    ValueRef,
)


class Runtime:
    def __init__(self, registry: OperatorRegistry | None = None) -> None:
        self.registry = registry or build_default_registry()

    @staticmethod
    def _channel_is_unhealthy(parent: TransactionResult, channels: set[str]) -> bool:
        """Field-sensitive trust propagation for dependency edges."""
        if "explicit" in channels:
            return parent.status != "PASS"
        if any(":audited_result" in channel for channel in channels):
            return parent.status != "PASS"
        if any(":result" in channel for channel in channels):
            if parent.status in {"ERROR", "TAINTED"} or parent.unhealthy_dependencies:
                return True
            if parent.local_status == "PASS":
                return False
            failed_checks = {name for name, check in parent.checks.items() if check.status != "PASS"}
            return not failed_checks.issubset({"value", "dependency"})
        return parent.status != "PASS"

    @staticmethod
    def _field_value(result: TransactionResult, field: str) -> Any:
        if field == "result":
            return result.computed_result
        if field == "audited_result":
            return result.audited_result
        raise KeyError(f"Unsupported reference field: {field}")

    def _resolve_target_value(
        self,
        target: str,
        field: str,
        *,
        results: dict[str, TransactionResult],
        fixed_values: dict[str, Any] | None,
    ) -> Any:
        if fixed_values is not None and target in fixed_values:
            # Fixed-point iterates expose one current state for both channels.
            return fixed_values[target]
        if target not in results:
            raise KeyError(f"Referenced transaction not executed: {target}")
        return self._field_value(results[target], field)

    def _resolve(
        self,
        value: Any,
        *,
        current_tx_id: str,
        ledger: MatrixLedger,
        execution_traversal: str,
        physical_order: list[str] | None,
        results: dict[str, TransactionResult],
        fixed_values: dict[str, Any] | None = None,
        temporal_lookup: dict[tuple[str, int], str] | None = None,
    ) -> Any:
        if isinstance(value, ValueRef):
            return self._resolve_target_value(
                value.tx_id,
                value.field,
                results=results,
                fixed_values=fixed_values,
            )
        if isinstance(value, TemporalRef):
            target = resolve_temporal_target(
                ledger,
                current_tx_id,
                value,
                temporal_lookup,
            )
            if target is None:
                if value.has_default:
                    return self._resolve(
                        value.default,
                        current_tx_id=current_tx_id,
                        ledger=ledger,
                        execution_traversal=execution_traversal,
                        physical_order=physical_order,
                        results=results,
                        fixed_values=fixed_values,
                        temporal_lookup=temporal_lookup,
                    )
                raise KeyError(
                    f"No temporal target for {current_tx_id}: series={value.series_id}, lag={value.lag}"
                )
            return self._resolve_target_value(
                target,
                value.field,
                results=results,
                fixed_values=fixed_values,
            )
        if isinstance(value, MatrixRef):
            target = resolve_matrix_target(
                ledger,
                current_tx_id,
                value,
                execution_traversal,
                physical_order,
            )
            if target is None:
                if value.has_default:
                    return self._resolve(
                        value.default,
                        current_tx_id=current_tx_id,
                        ledger=ledger,
                        execution_traversal=execution_traversal,
                        physical_order=physical_order,
                        results=results,
                        fixed_values=fixed_values,
                        temporal_lookup=temporal_lookup,
                    )
                raise KeyError(f"No {value.relation} neighbour for {current_tx_id}")
            return self._resolve_target_value(
                target,
                value.field,
                results=results,
                fixed_values=fixed_values,
            )
        if isinstance(value, dict):
            return {
                str(k): self._resolve(
                    v,
                    current_tx_id=current_tx_id,
                    ledger=ledger,
                    execution_traversal=execution_traversal,
                    physical_order=physical_order,
                    results=results,
                    fixed_values=fixed_values,
                    temporal_lookup=temporal_lookup,
                )
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [
                self._resolve(
                    v,
                    current_tx_id=current_tx_id,
                    ledger=ledger,
                    execution_traversal=execution_traversal,
                    physical_order=physical_order,
                    results=results,
                    fixed_values=fixed_values,
                    temporal_lookup=temporal_lookup,
                )
                for v in value
            ]
        if isinstance(value, tuple):
            return tuple(
                self._resolve(
                    v,
                    current_tx_id=current_tx_id,
                    ledger=ledger,
                    execution_traversal=execution_traversal,
                    physical_order=physical_order,
                    results=results,
                    fixed_values=fixed_values,
                    temporal_lookup=temporal_lookup,
                )
                for v in value
            )
        return value

    @staticmethod
    def _execution_traversal(ledger: MatrixLedger, requested: str | None) -> str:
        selected = requested if requested is not None else ledger.traversals.get("execute", "dependency_topological")
        if not isinstance(selected, str):
            raise TraversalSemanticError("traversals.execute must be a single traversal name")
        if selected != "dependency_topological" and selected not in PHYSICAL_TRAVERSALS:
            raise TraversalSemanticError(f"Unsupported execution traversal: {selected}")
        return selected

    def _unhealthy_parents(
        self,
        tx_id: str,
        *,
        results: dict[str, TransactionResult],
        dependency_edges: dict[str, dict[str, set[str]]],
        ignore: set[str] | None = None,
    ) -> list[str]:
        ignored = ignore or set()
        return sorted(
            dep
            for dep in dependency_edges[tx_id]
            if dep not in ignored
            and results.get(dep)
            and self._channel_is_unhealthy(results[dep], dependency_edges[tx_id][dep])
        )

    @staticmethod
    def _source_check(ledger: MatrixLedger, tx: Any, resolved_base: Any, counterfactual: bool) -> CheckResult:
        if counterfactual and tx.source_id is not None:
            return CheckResult(
                "PASS",
                "Counterfactual branch: observational source equality is not required",
            )
        return source_check(ledger, tx, resolved_base)

    def _execute_intervened(
        self,
        tx_id: str,
        intervention: dict[str, Any],
        *,
        ledger: MatrixLedger,
        deps: dict[str, set[str]],
        effective_declared: dict[str, Any],
        corrections_applied: dict[str, list[str]],
        fdcs_context: str,
    ) -> TransactionResult:
        tx = ledger.transactions[tx_id]
        value = intervention["value"]
        checks = {
            "type": CheckResult("PASS", "Intervention value accepted as an explicit counterfactual state"),
            "domain": CheckResult("PASS", "Structural equation bypassed by do_set"),
            "value": CheckResult("PASS", "Intervention defines the branch value"),
            "source": CheckResult("PASS", "Incoming observational source relation cut by intervention"),
            "dependency_declaration": CheckResult("PASS", "Incoming structural dependencies cut by intervention"),
            "dependency": CheckResult("PASS", "Intervened node has no active incoming causal parents"),
            "intervention": CheckResult("PASS", f"Executed {intervention['id']} as do_set"),
        }
        return TransactionResult(
            tx_id=tx_id,
            operator=tx.operator,
            operator_version=f"do_set@0.7:{tx.operator}",
            computed_result=value,
            structural_result=None,
            audited_result=value,
            status="PASS",
            local_status="PASS",
            checks=checks,
            dependencies=sorted(deps[tx_id]),
            unhealthy_dependencies=[],
            dependency_channels={},
            coordinate=ledger.coordinates.get(tx_id),
            time_index=int(tx.time_index),
            series_id=tx.series_id or tx_id,
            original_declared_result=tx.declared_result,
            effective_declared_result=effective_declared[tx_id],
            corrections_applied=list(corrections_applied[tx_id]),
            intervened=True,
            intervention_ids=[str(intervention["id"])],
            intervention_kinds=["do_set"],
            fdcs_context=fdcs_context,
        )

    def _execute_one(
        self,
        tx_id: str,
        *,
        ledger: MatrixLedger,
        active_traversal: str,
        physical_order: list[str] | None,
        results: dict[str, TransactionResult],
        dependency_edges: dict[str, dict[str, set[str]]],
        deps: dict[str, set[str]],
        effective_declared: dict[str, Any],
        corrections_applied: dict[str, list[str]],
        temporal_lookup: dict[tuple[str, int], str],
        counterfactual: bool = False,
        soft_intervention: dict[str, Any] | None = None,
    ) -> TransactionResult:
        tx = ledger.transactions[tx_id]
        unhealthy = self._unhealthy_parents(
            tx_id,
            results=results,
            dependency_edges=dependency_edges,
        )
        try:
            spec = self.registry.get(tx.operator)
        except MMLCError as exc:
            return TransactionResult(
                tx_id=tx_id,
                operator=tx.operator,
                operator_version=f"{tx.operator}@unknown",
                status="ERROR",
                local_status="ERROR",
                checks={
                    "operator": CheckResult("FAIL", str(exc)),
                    "dependency": dependency_health_check(unhealthy),
                },
                dependencies=sorted(deps[tx_id]),
                unhealthy_dependencies=unhealthy,
                dependency_channels={dep: sorted(dependency_edges[tx_id][dep]) for dep in deps[tx_id]},
                coordinate=ledger.coordinates.get(tx_id),
                time_index=int(tx.time_index),
                series_id=tx.series_id or tx_id,
                original_declared_result=tx.declared_result,
                effective_declared_result=effective_declared[tx_id],
                corrections_applied=list(corrections_applied[tx_id]),
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

        result = TransactionResult(
            tx_id=tx_id,
            operator=tx.operator,
            operator_version=spec.lock_name,
            dependencies=sorted(deps[tx_id]),
            coordinate=ledger.coordinates.get(tx_id),
            time_index=int(tx.time_index),
            series_id=tx.series_id or tx_id,
            original_declared_result=tx.declared_result,
            effective_declared_result=effective_declared[tx_id],
            corrections_applied=list(corrections_applied[tx_id]),
        )
        result.unhealthy_dependencies = unhealthy
        result.dependency_channels = {dep: sorted(dependency_edges[tx_id][dep]) for dep in deps[tx_id]}
        try:
            resolve_args = {
                "current_tx_id": tx_id,
                "ledger": ledger,
                "execution_traversal": active_traversal,
                "physical_order": physical_order,
                "results": results,
                "temporal_lookup": temporal_lookup,
            }
            base = self._resolve(tx.base, **resolve_args)
            operand = self._resolve(tx.operand, **resolve_args)
            context = self._resolve(tx.context, **resolve_args)
            spec.type_check(base, operand, context)
            result.checks["type"] = CheckResult("PASS")
            spec.domain_check(base, operand, context)
            result.checks["domain"] = CheckResult("PASS")
            structural_computed = spec.evaluator(base, operand, context)
            computed = apply_soft_intervention(structural_computed, soft_intervention) if soft_intervention else structural_computed
            declared = effective_declared[tx_id]
            audited = computed if declared is None else self._resolve(declared, **resolve_args)
            result.structural_result = structural_computed
            result.computed_result = computed
            result.audited_result = audited
            if soft_intervention:
                equivalent, detail = equivalent_value(computed, audited, ledger.audit_policy.numeric_tolerance)
                residual = 0 if equivalent else (audited - computed if hasattr(audited, "__sub__") else None)
                result.checks["value"] = CheckResult(
                    "PASS" if equivalent else "FAIL",
                    "Soft-intervened structural equation satisfied" if equivalent else detail,
                    residual=residual,
                )
                result.checks["intervention"] = CheckResult(
                    "PASS",
                    f"Executed {soft_intervention['id']} as soft_affine: scale={soft_intervention.get('scale', 1)}, shift={soft_intervention.get('shift', 0)}",
                )
                result.intervened = True
                result.intervention_ids = [str(soft_intervention["id"])]
                result.intervention_kinds = ["soft_affine"]
                result.operator_version = f"{spec.lock_name}|soft_affine@0.7"
            else:
                residual = spec.auditor(base, operand, audited, context)
                result.checks["value"] = value_check(
                    residual,
                    base,
                    operand,
                    audited,
                    ledger.audit_policy.numeric_tolerance,
                )
            result.checks["source"] = self._source_check(ledger, tx, base, counterfactual)
            result.checks["dependency_declaration"] = dependency_declaration_check(tx, set(ledger.transactions))
            result.checks["dependency"] = dependency_health_check(unhealthy)

            local_required = [name for name in ledger.audit_policy.required_checks if name != "dependency"]
            result.local_status = (
                "PASS"
                if all(result.checks.get(name, CheckResult("FAIL")).status == "PASS" for name in local_required)
                else "FAIL"
            )
            if result.local_status == "FAIL":
                result.status = "FAIL"
            elif unhealthy:
                result.status = "TAINTED"
            else:
                result.status = "PASS"
        except MMLCError as exc:
            result.error_type = type(exc).__name__
            result.error_message = str(exc)
            if "type" not in result.checks:
                result.checks["type"] = CheckResult("FAIL", str(exc))
            elif "domain" not in result.checks:
                result.checks["domain"] = CheckResult("FAIL", str(exc))
            result.checks["dependency"] = dependency_health_check(unhealthy)
            result.local_status = "ERROR"
            result.status = "ERROR"
        except Exception as exc:
            result.error_type = type(exc).__name__
            result.error_message = str(exc)
            result.checks["runtime"] = CheckResult("FAIL", str(exc))
            result.checks["dependency"] = dependency_health_check(unhealthy)
            result.local_status = "ERROR"
            result.status = "ERROR"
        return result

    def _execute_fixed_group(
        self,
        group: FixedPointGroup,
        *,
        ledger: MatrixLedger,
        active_traversal: str,
        physical_order: list[str] | None,
        results: dict[str, TransactionResult],
        dependency_edges: dict[str, dict[str, set[str]]],
        deps: dict[str, set[str]],
        effective_declared: dict[str, Any],
        corrections_applied: dict[str, list[str]],
        temporal_lookup: dict[tuple[str, int], str],
        priority: list[str],
        counterfactual: bool = False,
        intervention_map: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[list[str], dict[str, Any]]:
        if group.method != "jacobi":
            raise TraversalSemanticError(f"Unsupported fixed-point method: {group.method}")
        members = set(group.members)
        ordered_members = sorted(group.members, key=lambda tx_id: (priority.index(tx_id) if tx_id in priority else 10**9, tx_id))
        current = {tx_id: group.initial_values.get(tx_id, 0.0) for tx_id in ordered_members}
        converged = False
        final_delta: float | None = None
        iterations = 0
        error: Exception | None = None
        try:
            for iteration in range(1, group.max_iterations + 1):
                candidate: dict[str, Any] = {}
                for tx_id in ordered_members:
                    tx = ledger.transactions[tx_id]
                    intervention = (intervention_map or {}).get(tx_id)
                    if intervention and intervention.get("kind") == "do_set":
                        candidate[tx_id] = intervention["value"]
                        continue
                    spec = self.registry.get(tx.operator)
                    resolve_args = {
                        "current_tx_id": tx_id,
                        "ledger": ledger,
                        "execution_traversal": active_traversal,
                        "physical_order": physical_order,
                        "results": results,
                        "fixed_values": current,
                        "temporal_lookup": temporal_lookup,
                    }
                    base = self._resolve(tx.base, **resolve_args)
                    operand = self._resolve(tx.operand, **resolve_args)
                    context = self._resolve(tx.context, **resolve_args)
                    spec.type_check(base, operand, context)
                    spec.domain_check(base, operand, context)
                    structural_value = spec.evaluator(base, operand, context)
                    candidate[tx_id] = apply_soft_intervention(structural_value, intervention) if intervention else structural_value
                final_delta = convergence_delta(current, candidate)
                current = candidate
                iterations = iteration
                if final_delta <= group.tolerance:
                    converged = True
                    break
        except Exception as exc:  # converted into structured group errors below
            error = exc

        group_results: dict[str, TransactionResult] = {}
        for tx_id in ordered_members:
            tx = ledger.transactions[tx_id]
            unhealthy = self._unhealthy_parents(
                tx_id,
                results=results,
                dependency_edges=dependency_edges,
                ignore=members,
            )
            try:
                spec = self.registry.get(tx.operator)
                operator_version = spec.lock_name
            except Exception:
                spec = None
                operator_version = f"{tx.operator}@unknown"
            result = TransactionResult(
                tx_id=tx_id,
                operator=tx.operator,
                operator_version=operator_version,
                dependencies=sorted(deps[tx_id]),
                unhealthy_dependencies=unhealthy,
                dependency_channels={dep: sorted(dependency_edges[tx_id][dep]) for dep in deps[tx_id]},
                coordinate=ledger.coordinates.get(tx_id),
                time_index=int(tx.time_index),
                series_id=tx.series_id or tx_id,
                original_declared_result=tx.declared_result,
                effective_declared_result=effective_declared[tx_id],
                corrections_applied=list(corrections_applied[tx_id]),
                fixed_point_group=group.group_id,
                fixed_point_iterations=iterations,
            )
            if error is not None or not converged or spec is None:
                message = str(error) if error is not None else (
                    f"Fixed-point group {group.group_id} did not converge in {group.max_iterations} iterations; delta={final_delta}"
                )
                result.status = "ERROR"
                result.local_status = "ERROR"
                result.error_type = type(error).__name__ if error is not None else "FixedPointConvergenceError"
                result.error_message = message
                result.checks["fixed_point"] = CheckResult("FAIL", message, scaled_residual=final_delta)
                result.checks["dependency"] = dependency_health_check(unhealthy)
                group_results[tx_id] = result
                continue
            try:
                intervention = (intervention_map or {}).get(tx_id)
                resolve_args = {
                    "current_tx_id": tx_id,
                    "ledger": ledger,
                    "execution_traversal": active_traversal,
                    "physical_order": physical_order,
                    "results": results,
                    "fixed_values": current,
                    "temporal_lookup": temporal_lookup,
                }
                computed = current[tx_id]
                declared = effective_declared[tx_id]
                audited = computed if declared is None else self._resolve(declared, **resolve_args)
                result.computed_result = computed
                result.audited_result = audited
                result.checks["type"] = CheckResult("PASS")
                result.checks["domain"] = CheckResult("PASS")
                result.checks["fixed_point"] = CheckResult(
                    "PASS",
                    f"Converged in {iterations} iterations; delta={final_delta:.3e}",
                    scaled_residual=final_delta,
                )
                if intervention and intervention.get("kind") == "do_set":
                    base = computed
                    operand = None
                    result.structural_result = None
                    result.intervened = True
                    result.intervention_ids = [str(intervention["id"])]
                    result.intervention_kinds = ["do_set"]
                    result.operator_version = f"do_set@0.7:{tx.operator}|fixed_point"
                    result.checks["value"] = CheckResult("PASS", "Hard intervention fixed the group member state")
                    result.checks["intervention"] = CheckResult(
                        "PASS", f"Executed {intervention['id']} inside fixed-point group and re-solved remaining members"
                    )
                else:
                    base = self._resolve(tx.base, **resolve_args)
                    operand = self._resolve(tx.operand, **resolve_args)
                    context = self._resolve(tx.context, **resolve_args)
                    structural = spec.evaluator(base, operand, context)
                    result.structural_result = structural
                    if intervention:
                        expected = apply_soft_intervention(structural, intervention)
                        equivalent, detail = equivalent_value(expected, audited, ledger.audit_policy.numeric_tolerance)
                        result.checks["value"] = CheckResult(
                            "PASS" if equivalent else "FAIL",
                            "Soft-intervened fixed-point equation satisfied" if equivalent else detail,
                            residual=0 if equivalent else None,
                        )
                        result.intervened = True
                        result.intervention_ids = [str(intervention["id"])]
                        result.intervention_kinds = ["soft_affine"]
                        result.operator_version = f"{spec.lock_name}|soft_affine@0.7|fixed_point"
                        result.checks["intervention"] = CheckResult(
                            "PASS", f"Executed {intervention['id']} inside fixed-point group and re-solved the cycle"
                        )
                    else:
                        residual = spec.auditor(base, operand, audited, context)
                        result.checks["value"] = value_check(
                            residual,
                            base,
                            operand,
                            audited,
                            ledger.audit_policy.numeric_tolerance,
                        )
                result.checks["source"] = self._source_check(ledger, tx, base, counterfactual)
                result.checks["dependency_declaration"] = dependency_declaration_check(tx, set(ledger.transactions))
                result.checks["dependency"] = dependency_health_check(unhealthy)
                local_required = [name for name in ledger.audit_policy.required_checks if name != "dependency"]
                result.local_status = (
                    "PASS"
                    if all(result.checks.get(name, CheckResult("FAIL")).status == "PASS" for name in local_required)
                    else "FAIL"
                )
                if result.local_status == "FAIL":
                    result.status = "FAIL"
                elif unhealthy:
                    result.status = "TAINTED"
                else:
                    result.status = "PASS"
            except Exception as exc:
                result.status = "ERROR"
                result.local_status = "ERROR"
                result.error_type = type(exc).__name__
                result.error_message = str(exc)
                result.checks["runtime"] = CheckResult("FAIL", str(exc))
            group_results[tx_id] = result

        for tx_id in ordered_members:
            results[tx_id] = group_results[tx_id]
        analysis = {
            "group_id": group.group_id,
            "members": ordered_members,
            "method": group.method,
            "converged": converged and error is None,
            "iterations": iterations,
            "final_delta": final_delta,
            "tolerance": group.tolerance,
            "max_iterations": group.max_iterations,
            "values": current,
            "interventions": [
                (intervention_map or {})[member]
                for member in ordered_members
                if member in (intervention_map or {})
            ],
            "re_solved_under_intervention": any(member in (intervention_map or {}) for member in ordered_members),
            "error": str(error) if error is not None else None,
        }
        return ordered_members, analysis

    def execute(
        self,
        ledger: MatrixLedger,
        deterministic: bool = False,
        execution_traversal: str | None = None,
        *,
        _fdcs_branch: bool = False,
        _fdcs_context: str | None = None,
        _fdcs_modulation: float | None = None,
        _interventions: list[dict[str, Any]] | None = None,
        _counterfactual: bool = False,
    ) -> RunResult:
        active_traversal = self._execution_traversal(ledger, execution_traversal)
        physical_order = physical_sequence(ledger, active_traversal) if active_traversal in PHYSICAL_TRAVERSALS else None
        dependency_edges = build_dependency_edges(ledger, active_traversal)
        intervention_audit = audit_intervention_set(ledger, _interventions or [])
        intervention_map = validate_interventions(ledger, _interventions or [])
        cut_edges = cut_incoming_edges(dependency_edges, intervention_map)
        deps = {tx_id: set(parents) for tx_id, parents in dependency_edges.items()}
        priority = physical_order or ledger.display_order
        plan, groups, _member_to_group = execution_units(ledger, deps, priority)
        effective_declared, corrections_applied, correction_analysis = apply_corrections(ledger)
        if _counterfactual:
            # Observational claims are retained on each transaction but are not
            # treated as counterfactual expected values.
            effective_declared = {tx_id: None for tx_id in ledger.transactions}
        temporal_lookup = temporal_index(ledger)
        results: dict[str, TransactionResult] = {}
        order: list[str] = []
        fixed_groups_analysis: dict[str, Any] = {}

        for kind, identifier in plan:
            if kind == "tx":
                active_intervention = intervention_map.get(identifier)
                if active_intervention and active_intervention.get("kind") == "do_set":
                    result = self._execute_intervened(
                        identifier,
                        active_intervention,
                        ledger=ledger,
                        deps=deps,
                        effective_declared=effective_declared,
                        corrections_applied=corrections_applied,
                        fdcs_context=str(_fdcs_context or "baseline"),
                    )
                else:
                    result = self._execute_one(
                        identifier,
                        ledger=ledger,
                        active_traversal=active_traversal,
                        physical_order=physical_order,
                        results=results,
                        dependency_edges=dependency_edges,
                        deps=deps,
                        effective_declared=effective_declared,
                        corrections_applied=corrections_applied,
                        temporal_lookup=temporal_lookup,
                        counterfactual=_counterfactual,
                        soft_intervention=active_intervention,
                    )
                result.fdcs_context = str(_fdcs_context or "baseline")
                results[identifier] = result
                order.append(identifier)
            elif kind == "group":
                members, group_analysis = self._execute_fixed_group(
                    groups[identifier],
                    ledger=ledger,
                    active_traversal=active_traversal,
                    physical_order=physical_order,
                    results=results,
                    dependency_edges=dependency_edges,
                    deps=deps,
                    effective_declared=effective_declared,
                    corrections_applied=corrections_applied,
                    temporal_lookup=temporal_lookup,
                    priority=priority,
                    counterfactual=_counterfactual,
                    intervention_map=intervention_map,
                )
                for member in members:
                    results[member].fdcs_context = str(_fdcs_context or "baseline")
                order.extend(members)
                fixed_groups_analysis[identifier] = group_analysis
            else:  # pragma: no cover - defensive
                raise TraversalSemanticError(f"Unknown execution unit kind: {kind}")

        local_failures, tainted, regions, global_audit = aggregate_audits(ledger, results)
        root_cause_analysis = build_root_cause_analysis(results, deps)
        constraint_audits = evaluate_constraints(ledger, results)
        constraint_failures = sorted(
            constraint_id for constraint_id, audit in constraint_audits.items()
            if audit.status == "FAIL"
        )
        constraint_errors = sorted(
            constraint_id for constraint_id, audit in constraint_audits.items()
            if audit.status == "ERROR"
        )
        cross_axis_conflicts = detect_cross_axis_conflicts(constraint_audits)
        repair_analysis = find_minimum_repair_sets(ledger, results, constraint_audits)
        temporal_analysis = build_temporal_analysis(ledger, dependency_edges, results)
        fixed_point_analysis = {
            "enabled": bool(ledger.fixed_point_groups),
            "groups": fixed_groups_analysis,
            "all_converged": all(item.get("converged", False) for item in fixed_groups_analysis.values()) if fixed_groups_analysis else True,
        }
        active_context = str(_fdcs_context or dict(ledger.fdcs or {}).get("base_context", dict(ledger.fdcs or {}).get("context", "baseline")))
        fdcs_projection = build_fdcs_projection(
            ledger,
            results,
            dependency_edges,
            context_id=active_context,
            context_modulation=_fdcs_modulation,
            cut_edges=cut_edges,
            interventions=list(intervention_map.values()),
            intervention_audit=intervention_audit,
        )

        if fdcs_projection.get("enabled") and not _fdcs_branch:
            config = dict(ledger.fdcs or {})
            _, continuous_plan = generate_continuous_ensemble_specs(
                ledger_version=semantic_profile(ledger),
                continuous_config=dict(config.get("continuous_uncertainty", {})),
                transaction_ids=ledger.transactions,
            )
            specs = context_specs(ledger)
            baseline_summary = {
                "context_id": active_context,
                "status": "OBSERVED",
                "global_audit": global_audit.get("status"),
                "semantic_hash": semantic_hash({
                    "context": active_context,
                    "values": {tx_id: results[tx_id].computed_result for tx_id in sorted(results)},
                    "statuses": {tx_id: results[tx_id].status for tx_id in sorted(results)},
                }),
                "execution_hash": semantic_hash({
                    "context": active_context,
                    "execution_order": order,
                    "execution_traversal": active_traversal,
                }),
                "context_modulation": fdcs_projection.get("context_modulation", 1.0),
                "interventions": [],
                "cut_edges": [],
                "changed_transactions": [],
                "deltas": {},
                "values": {tx_id: results[tx_id].computed_result for tx_id in sorted(results)},
                "projection": {
                    key: value for key, value in fdcs_projection.items()
                    if key not in {"contexts", "branch_order"}
                },
                "fixed_point_analysis": fixed_point_analysis,
                "counterfactual_declared_results_ignored": False,
            }
            baseline_summary["intervention_audit"] = {
                "status": "PASS", "errors": [], "conflicts": [], "redundancies": []
            }
            baseline_summary["differential_ledger"] = {
                "format": "MMLC-BRANCH-DIFF", "version": "0.9", "context_id": active_context,
                "record_count": 0, "changed_count": 0, "records": [],
                "head_hash": semantic_hash({"context": active_context, "records": []}),
                "append_only_order": "transaction_id_lexicographic",
            }
            branch_runs: dict[str, RunResult] = {}
            valid_specs = [spec for spec in specs if spec["intervention_audit"]["status"] != "FAIL"]
            invalid_specs = [spec for spec in specs if spec["intervention_audit"]["status"] == "FAIL"]
            if valid_specs:
                workers = max(1, min(int(config.get("parallel_workers", len(valid_specs))), len(valid_specs)))

                def _run_context(spec: dict[str, Any]) -> tuple[str, RunResult]:
                    run = self.execute(
                        ledger,
                        deterministic=deterministic,
                        execution_traversal=active_traversal,
                        _fdcs_branch=True,
                        _fdcs_context=str(spec["id"]),
                        _fdcs_modulation=float(spec["modulation"]),
                        _interventions=list(spec["interventions"]),
                        _counterfactual=True,
                    )
                    return str(spec["id"]), run

                if workers > 1:
                    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mmlc-fdcs") as executor:
                        futures = {executor.submit(_run_context, spec): spec for spec in valid_specs}
                        for future in as_completed(futures):
                            context_id, run = future.result()
                            branch_runs[context_id] = run
                else:
                    for spec in valid_specs:
                        context_id, run = _run_context(spec)
                        branch_runs[context_id] = run
            contexts: dict[str, Any] = {active_context: baseline_summary}
            spec_by_id = {str(spec["id"]): spec for spec in specs}
            for context_id in sorted(branch_runs):
                spec = spec_by_id[context_id]
                contexts[context_id] = branch_summary(
                    context_id=context_id,
                    modulation=float(spec["modulation"]),
                    run=branch_runs[context_id],
                    baseline_results=results,
                    intervention_audit=spec["intervention_audit"],
                    probability=spec.get("probability"),
                    policy_id=spec.get("policy_id"),
                    scenario_id=spec.get("scenario_id"),
                    cost=float(spec.get("cost", 0.0)),
                )
            for spec in invalid_specs:
                context_id = str(spec["id"])
                contexts[context_id] = {
                    "context_id": context_id,
                    "status": "CONFLICT",
                    "global_audit": "FAIL",
                    "semantic_hash": None,
                    "execution_hash": None,
                    "context_modulation": float(spec["modulation"]),
                    "probability": spec.get("probability"),
                    "policy_id": spec.get("policy_id"),
                    "scenario_id": spec.get("scenario_id"),
                    "cost": float(spec.get("cost", 0.0)),
                    "interventions": list(spec["interventions"]),
                    "intervention_audit": spec["intervention_audit"],
                    "cut_edges": [],
                    "changed_transactions": [],
                    "deltas": {},
                    "differential_ledger": None,
                    "values": {},
                    "projection": None,
                    "counterfactual_declared_results_ignored": True,
                }
            observed_transactions = config.get("observed_transactions", sorted(ledger.transactions))
            identifiability = build_identifiability_audit(
                contexts=contexts,
                base_context=active_context,
                observed_transactions=observed_transactions,
            )
            probability_analysis = build_probability_analysis(
                contexts=contexts,
                context_specs=specs,
                tolerance=float(dict(config.get("probability_model", {})).get("tolerance", 1.0e-12)),
            )
            continuous_analysis = build_continuous_approximation_analysis(continuous_plan)
            policy_analysis = build_policy_analysis(
                contexts=contexts,
                context_specs=specs,
                probability_analysis=probability_analysis,
                policy_config=dict(config.get("policy_selection", {})),
            )
            information_value_analysis = build_information_value_analysis(
                contexts=contexts,
                context_specs=specs,
                probability_analysis=probability_analysis,
                policy_config=dict(config.get("policy_selection", {})),
                config=dict(config.get("information_value", {})),
            )
            observation_plan = build_observation_plan(
                contexts=contexts,
                base_context=active_context,
                observed_transactions=observed_transactions,
                config=dict(config.get("observation_planning", {})),
                all_transactions=sorted(ledger.transactions),
            )
            branch_order = [active_context, *sorted(context_id for context_id in contexts if context_id != active_context)]
            fdcs_projection = {
                **fdcs_projection,
                "status": "PARTIAL" if invalid_specs else ("EXECUTED" if specs else "PROJECTED"),
                "base_context": active_context,
                "execution_mode": "parallel_thread_pool" if len(valid_specs) > 1 and int(config.get("parallel_workers", len(valid_specs))) > 1 else "deterministic_sequential",
                "parallel_workers": max(1, min(int(config.get("parallel_workers", max(1, len(valid_specs)))), max(1, len(valid_specs)))),
                "branch_order": branch_order,
                "contexts": contexts,
                "identifiability_audit": identifiability,
                "probability_analysis": probability_analysis,
                "continuous_approximation_analysis": continuous_analysis,
                "policy_analysis": policy_analysis,
                "information_value_analysis": information_value_analysis,
                "observation_plan": observation_plan,
                "intervention_conflict_count": sum(len(spec["intervention_audit"]["conflicts"]) + len(spec["intervention_audit"]["errors"]) for spec in specs),
                "all_contexts_executed": all(item.get("status") in {"OBSERVED", "EXECUTED"} for item in contexts.values()),
            }

        global_audit["constraint_failures"] = constraint_failures
        global_audit["constraint_errors"] = constraint_errors
        global_audit["cross_axis_conflict_count"] = len(cross_axis_conflicts)
        global_audit["matrix_constraints_enabled"] = bool(ledger.constraints)
        global_audit["temporal_enabled"] = temporal_analysis["enabled"]
        global_audit["fixed_point_enabled"] = fixed_point_analysis["enabled"]
        global_audit["fixed_point_all_converged"] = fixed_point_analysis["all_converged"]
        global_audit["corrections_enabled"] = correction_analysis["enabled"]
        global_audit["fdcs_projection_enabled"] = fdcs_projection["enabled"]
        global_audit["fdcs_status"] = fdcs_projection.get("status", "DISABLED")
        global_audit["fdcs_context_count"] = len(fdcs_projection.get("contexts", {}))
        global_audit["fdcs_intervention_conflicts"] = int(fdcs_projection.get("intervention_conflict_count", 0))
        global_audit["fdcs_all_contexts_executed"] = fdcs_projection.get("all_contexts_executed", True)
        global_audit["fdcs_probability_status"] = (fdcs_projection.get("probability_analysis") or {}).get("status", "DISABLED")
        global_audit["fdcs_continuous_status"] = (fdcs_projection.get("continuous_approximation_analysis") or {}).get("status", "DISABLED")
        global_audit["fdcs_policy_status"] = (fdcs_projection.get("policy_analysis") or {}).get("status", "DISABLED")
        global_audit["fdcs_information_value_status"] = (fdcs_projection.get("information_value_analysis") or {}).get("status", "DISABLED")
        global_audit["fdcs_observation_plan_status"] = (fdcs_projection.get("observation_plan") or {}).get("status", "DISABLED")
        if (
            constraint_failures
            or constraint_errors
            or not fixed_point_analysis["all_converged"]
            or global_audit["fdcs_probability_status"] == "FAIL"
            or global_audit["fdcs_continuous_status"] == "FAIL"
            or global_audit["fdcs_policy_status"] == "FAIL"
            or global_audit["fdcs_information_value_status"] == "FAIL"
        ):
            global_audit["status"] = "FAIL"

        configured_display = ledger.traversals.get("display", ["left_to_right", "right_to_left"])
        if isinstance(configured_display, str):
            configured_display = [configured_display]
        traversal_names: list[str] = []
        for name in [*configured_display, "top_to_bottom", "bottom_to_top"]:
            if name in PHYSICAL_TRAVERSALS and name not in traversal_names:
                traversal_names.append(name)
        traversal_logs = [
            traverse(ledger, name, order, deps, role="execute" if name == active_traversal else "display", deterministic=deterministic)
            for name in traversal_names
        ]
        traversal_logs.append(
            traverse(ledger, "dependency_topological", order, deps, role="execute" if active_traversal == "dependency_topological" else "graph", deterministic=deterministic)
        )
        for tx_id in sorted(set(local_failures) | set(tainted)):
            traversal_logs.append(
                traverse(ledger, "reverse_dependency", order, deps, start=tx_id, role="audit", deterministic=deterministic)
            )

        semantic_payload = {
            "ledger_id": ledger.ledger_id,
            "version": ledger.version,
            "operator_lock": self.registry.lock(),
            "transactions": {
                tx_id: {
                    "computed_result": results[tx_id].computed_result,
                    "audited_result": results[tx_id].audited_result,
                    "status": results[tx_id].status,
                    "local_status": results[tx_id].local_status,
                    "checks": results[tx_id].checks,
                    "dependencies": sorted(deps[tx_id]),
                    "dependency_channels": results[tx_id].dependency_channels,
                    "root_causes": results[tx_id].root_causes,
                    "time_index": results[tx_id].time_index,
                    "series_id": results[tx_id].series_id,
                    "corrections_applied": results[tx_id].corrections_applied,
                    "fixed_point_group": results[tx_id].fixed_point_group,
                    "structural_result": results[tx_id].structural_result,
                    "intervened": results[tx_id].intervened,
                    "intervention_ids": results[tx_id].intervention_ids,
                    "intervention_kinds": results[tx_id].intervention_kinds,
                    "fdcs_context": results[tx_id].fdcs_context,
                }
                for tx_id in sorted(results)
            },
            "global_audit": global_audit,
            "root_cause_analysis": root_cause_analysis,
            "constraint_audits": constraint_audits,
            "cross_axis_conflicts": cross_axis_conflicts,
            "repair_analysis": repair_analysis,
            "temporal_analysis": temporal_analysis,
            "fixed_point_analysis": fixed_point_analysis,
            "correction_analysis": correction_analysis,
            "fdcs_projection": fdcs_projection,
        }
        digest = semantic_hash(semantic_payload)
        execution_payload = {
            "semantic_hash": digest,
            "execution_traversal": active_traversal,
            "execution_order": order,
            "layout": ledger.layout,
            "coordinates": ledger.coordinates,
            "operator_lock": self.registry.lock(),
        }
        execution_digest = semantic_hash(execution_payload)
        manifest = {
            "ledger_id": ledger.ledger_id,
            "ledger_version": ledger.version,
            "runtime_version": __version__,
            "operator_lock": self.registry.lock(),
            "semantic_hash": digest,
            "execution_hash": execution_digest,
            "execution_traversal": active_traversal,
            "deterministic": deterministic,
            "correction_chain_head": correction_analysis["head_hash"],
            "features": [
                "symbolic_numeric_exchange",
                "dependency_taint",
                "root_cause_paths",
                "matrix_coordinates",
                "multidirectional_traversal",
                "relative_matrix_references",
                "row_column_block_constraints",
                "cross_axis_conflict_audit",
                "minimum_support_repair",
                "constraint_factor_graph",
                "temporal_index",
                "lagged_dependencies",
                "declared_fixed_point_groups",
                "append_only_corrections",
                "fdcs_projection",
                "executable_virtual_interventions",
                "parallel_context_branches",
                "direction_asymmetric_causal_weights",
                "fractal_level_decay",
                "soft_affine_interventions",
                "fixed_point_intervention_resolve",
                "branch_differential_ledger",
                "intervention_conflict_audit",
                "ledger_identifiability_audit",
                "deterministic_continuous_approximation",
                "gaussian_copula_correlated_uncertainty",
                "cost_aware_observation_planning",
                "expected_value_of_information",
                "finite_horizon_sequential_decision",
                "stable_public_api_v1",
                "packaged_mmlf_schemas",
                "deterministic_migration_v1",
            ],
        }
        return RunResult(
            ledger_id=ledger.ledger_id,
            runtime_version=__version__,
            execution_order=order,
            execution_traversal=active_traversal,
            transactions=results,
            local_failures=local_failures,
            tainted_transactions=tainted,
            region_audits=regions,
            global_audit=global_audit,
            traversals=traversal_logs,
            root_cause_analysis=root_cause_analysis,
            constraint_audits=constraint_audits,
            cross_axis_conflicts=cross_axis_conflicts,
            repair_analysis=repair_analysis,
            temporal_analysis=temporal_analysis,
            fixed_point_analysis=fixed_point_analysis,
            correction_analysis=correction_analysis,
            fdcs_projection=fdcs_projection,
            semantic_hash=digest,
            execution_hash=execution_digest,
            manifest=manifest,
        )
