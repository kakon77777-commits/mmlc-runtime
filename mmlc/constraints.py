from __future__ import annotations

from itertools import combinations
from typing import Any

import sympy as sp

from .types import (
    ConstraintResult,
    MatrixConstraint,
    MatrixLedger,
    RepairProposal,
    RepairReport,
    TransactionResult,
)
from .values import equivalent_value, is_numeric, is_symbolic

SUPPORTED_FIELDS = {"result", "audited_result"}
SUPPORTED_KINDS = {"sum_equals", "all_equal"}


def constraint_members_from_scope(
    layout: list[list[str | None]],
    transactions: dict[str, Any],
    scope: dict[str, Any],
) -> tuple[str, tuple[str, ...]]:
    axis = str(scope.get("type", "cells"))
    rows = len(layout)
    cols = len(layout[0]) if rows else 0

    if axis == "row":
        index = int(scope["index"])
        if index < 0 or index >= rows:
            raise ValueError(f"row constraint index out of range: {index}")
        members = tuple(x for x in layout[index] if x is not None)
    elif axis == "column":
        index = int(scope["index"])
        if index < 0 or index >= cols:
            raise ValueError(f"column constraint index out of range: {index}")
        members = tuple(layout[r][index] for r in range(rows) if layout[r][index] is not None)
    elif axis == "block":
        r0 = int(scope["row_start"])
        r1 = int(scope["row_end"])
        c0 = int(scope["column_start"])
        c1 = int(scope["column_end"])
        if not (0 <= r0 < r1 <= rows and 0 <= c0 < c1 <= cols):
            raise ValueError(f"invalid block scope: rows=({r0},{r1}), columns=({c0},{c1})")
        members = tuple(
            layout[r][c]
            for r in range(r0, r1)
            for c in range(c0, c1)
            if layout[r][c] is not None
        )
    elif axis == "region":
        region = str(scope["region"])
        members = tuple(tx_id for tx_id, tx in transactions.items() if tx.region == region)
    elif axis == "cells":
        members = tuple(str(x) for x in scope.get("ids", []))
    else:
        raise ValueError(f"unsupported constraint scope type: {axis}")

    if not members:
        raise ValueError("constraint scope selects no transactions")
    unknown = sorted(set(members) - set(transactions))
    if unknown:
        raise ValueError(f"constraint references unknown transactions: {unknown}")
    return axis, members


def _field_value(result: TransactionResult, field: str) -> Any:
    if field == "result":
        return result.computed_result
    if field == "audited_result":
        return result.audited_result
    raise ValueError(f"unsupported constraint field: {field}")


def evaluate_constraints(
    ledger: MatrixLedger,
    results: dict[str, TransactionResult],
) -> dict[str, ConstraintResult]:
    audits: dict[str, ConstraintResult] = {}
    for constraint in ledger.constraints:
        try:
            values = [_field_value(results[tx_id], constraint.field) for tx_id in constraint.members]
            if any(results[tx_id].status == "ERROR" for tx_id in constraint.members):
                audits[constraint.constraint_id] = ConstraintResult(
                    constraint_id=constraint.constraint_id,
                    kind=constraint.kind,
                    axis=constraint.axis,
                    field=constraint.field,
                    members=constraint.members,
                    status="ERROR",
                    target=constraint.target,
                    detail="One or more member transactions are ERROR",
                )
                continue

            tolerance = ledger.audit_policy.numeric_tolerance if constraint.tolerance is None else constraint.tolerance
            if constraint.kind == "sum_equals":
                observed = sum(values)
                residual = sp.simplify(observed - constraint.target) if any(is_symbolic(v) for v in values) else observed - constraint.target
                equivalent, detail = equivalent_value(observed, constraint.target, tolerance)
                status = "PASS" if equivalent else "FAIL"
            elif constraint.kind == "all_equal":
                expected = constraint.target if constraint.target is not None else values[0]
                comparisons = [equivalent_value(value, expected, tolerance)[0] for value in values]
                status = "PASS" if all(comparisons) else "FAIL"
                observed = tuple(values)
                residual = sum(0 if ok else 1 for ok in comparisons)
                detail = f"{sum(comparisons)}/{len(comparisons)} members equal target"
            else:
                raise ValueError(f"unsupported constraint kind: {constraint.kind}")

            audits[constraint.constraint_id] = ConstraintResult(
                constraint_id=constraint.constraint_id,
                kind=constraint.kind,
                axis=constraint.axis,
                field=constraint.field,
                members=constraint.members,
                status=status,
                observed=observed,
                target=constraint.target,
                residual=residual,
                detail=detail,
            )
        except Exception as exc:
            audits[constraint.constraint_id] = ConstraintResult(
                constraint_id=constraint.constraint_id,
                kind=constraint.kind,
                axis=constraint.axis,
                field=constraint.field,
                members=constraint.members,
                status="ERROR",
                target=constraint.target,
                detail=str(exc),
            )
    return audits


def detect_cross_axis_conflicts(audits: dict[str, ConstraintResult]) -> list[dict[str, Any]]:
    failed = [audit for audit in audits.values() if audit.status == "FAIL"]
    conflicts: list[dict[str, Any]] = []
    for left, right in combinations(sorted(failed, key=lambda x: x.constraint_id), 2):
        if left.axis == right.axis:
            continue
        intersection = sorted(set(left.members) & set(right.members))
        if not intersection:
            continue
        conflicts.append({
            "constraints": [left.constraint_id, right.constraint_id],
            "axes": [left.axis, right.axis],
            "intersection": intersection,
        })
    return conflicts


def _sympy_number(value: Any) -> sp.Expr:
    if isinstance(value, sp.Basic):
        return value
    return sp.nsimplify(value)


def _current_value(result: TransactionResult, field: str) -> Any:
    return _field_value(result, field)


def find_minimum_repair_sets(
    ledger: MatrixLedger,
    results: dict[str, TransactionResult],
    audits: dict[str, ConstraintResult],
    *,
    max_support: int = 3,
    max_proposals: int = 64,
) -> RepairReport:
    failed = [audit for audit in audits.values() if audit.status == "FAIL"]
    if not failed:
        return RepairReport(
            status="NOT_NEEDED",
            method="minimum_support_linear_repair",
            minimal_size=0,
            proposals=[],
            ambiguous=False,
            searched_supports=0,
            exact=True,
            detail="All matrix constraints pass",
        )

    usable = [
        audit for audit in audits.values()
        if audit.status in {"PASS", "FAIL"}
        and audit.kind == "sum_equals"
        and audit.field in SUPPORTED_FIELDS
        and all(is_numeric(_current_value(results[tx_id], audit.field)) or is_symbolic(_current_value(results[tx_id], audit.field)) for tx_id in audit.members)
    ]
    failed_ids = {audit.constraint_id for audit in failed}
    failed_fields = {audit.field for audit in failed}
    if len(failed_fields) != 1:
        return RepairReport(
            status="UNSUPPORTED",
            method="minimum_support_linear_repair",
            minimal_size=None,
            proposals=[],
            ambiguous=False,
            searched_supports=0,
            exact=False,
            detail="A repair proposal currently targets exactly one value channel at a time",
        )
    repair_field = next(iter(failed_fields))
    usable = [audit for audit in usable if audit.field == repair_field]
    usable_ids = {audit.constraint_id for audit in usable}
    if not failed_ids.issubset(usable_ids):
        return RepairReport(
            status="UNSUPPORTED",
            method="minimum_support_linear_repair",
            minimal_size=None,
            proposals=[],
            ambiguous=False,
            searched_supports=0,
            exact=False,
            detail="Exact repair currently supports numeric/symbolic sum_equals constraints only",
        )

    candidate_cells = sorted(set().union(*(set(audit.members) for audit in failed)))
    searched = 0
    proposals: list[RepairProposal] = []
    support_limit = min(max_support, len(candidate_cells))

    for size in range(1, support_limit + 1):
        for subset in combinations(candidate_cells, size):
            searched += 1
            variables = sp.symbols(f"d0:{size}")
            equations: list[sp.Expr] = []
            for audit in usable:
                residual = _sympy_number(audit.residual)
                correction = sum(
                    variables[index]
                    for index, tx_id in enumerate(subset)
                    if tx_id in audit.members
                )
                equations.append(sp.simplify(correction + residual))
            solution_set = sp.linsolve(equations, variables)
            if solution_set is sp.EmptySet or not solution_set:
                continue
            solution = next(iter(solution_set))
            free = sorted(set().union(*(expr.free_symbols for expr in solution)), key=str)
            selected = {symbol: sp.Integer(0) for symbol in free}
            solved = tuple(sp.simplify(expr.subs(selected)) for expr in solution)
            if any(expr.free_symbols for expr in solved):
                continue
            deltas = {tx_id: delta for tx_id, delta in zip(subset, solved) if sp.simplify(delta) != 0}
            if not deltas:
                continue
            if len(deltas) < size:
                # A smaller support should be discovered in an earlier round.
                continue

            # Verify every usable constraint exactly after applying the proposal.
            valid = True
            preserved: list[str] = []
            for audit in usable:
                corrected = _sympy_number(audit.observed) + sum(
                    deltas.get(tx_id, 0) for tx_id in audit.members
                )
                if sp.simplify(corrected - _sympy_number(audit.target)) != 0:
                    valid = False
                    break
                preserved.append(audit.constraint_id)
            if not valid:
                continue

            corrected_values = {
                tx_id: sp.simplify(_sympy_number(_current_value(results[tx_id], repair_field)) + delta)
                for tx_id, delta in deltas.items()
            }
            proposals.append(RepairProposal(
                cells=tuple(sorted(deltas)),
                field=repair_field,
                deltas={tx_id: deltas[tx_id] for tx_id in sorted(deltas)},
                corrected_values={tx_id: corrected_values[tx_id] for tx_id in sorted(corrected_values)},
                preserves_constraints=tuple(sorted(preserved)),
            ))
            if len(proposals) >= max_proposals:
                break
        if proposals:
            return RepairReport(
                status="SOLVED",
                method="minimum_support_linear_repair",
                minimal_size=size,
                proposals=proposals,
                ambiguous=len(proposals) > 1,
                searched_supports=searched,
                exact=True,
                detail="All passing and failing linear sum constraints are satisfied by each proposal",
            )

    return RepairReport(
        status="UNRESOLVED",
        method="minimum_support_linear_repair",
        minimal_size=None,
        proposals=[],
        ambiguous=False,
        searched_supports=searched,
        exact=False,
        detail=f"No repair found with support <= {support_limit}",
    )
