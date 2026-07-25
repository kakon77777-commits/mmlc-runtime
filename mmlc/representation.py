from __future__ import annotations

from typing import Any

from .types import MatrixLedger, RunResult
from .values import equivalent_value


def flat_table_projection(ledger: MatrixLedger, run: RunResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tx_id in ledger.display_order:
        coord = ledger.coordinates[tx_id]
        result = run.transactions[tx_id]
        rows.append({
            "tx_id": tx_id,
            "row": coord.row,
            "column": coord.column,
            "region": ledger.transactions[tx_id].region,
            "computed_result": result.computed_result,
            "audited_result": result.audited_result,
            "local_status": result.local_status,
            "status": result.status,
        })
    return rows


def constraint_factor_graph(ledger: MatrixLedger) -> dict[str, Any]:
    variables = [
        {
            "id": tx_id,
            "row": ledger.coordinates[tx_id].row,
            "column": ledger.coordinates[tx_id].column,
        }
        for tx_id in ledger.display_order
    ]
    constraints = [
        {
            "id": constraint.constraint_id,
            "kind": constraint.kind,
            "axis": constraint.axis,
            "field": constraint.field,
            "target": constraint.target,
        }
        for constraint in ledger.constraints
    ]
    edges = [
        {"variable": tx_id, "constraint": constraint.constraint_id}
        for constraint in ledger.constraints
        for tx_id in constraint.members
    ]
    return {"variables": variables, "constraints": constraints, "edges": edges}


def reference_constraint_audit(ledger: MatrixLedger, run: RunResult) -> dict[str, dict[str, Any]]:
    """Independent flat-table reference implementation for E4 comparison."""
    table = {row["tx_id"]: row for row in flat_table_projection(ledger, run)}
    output: dict[str, dict[str, Any]] = {}
    for constraint in ledger.constraints:
        key = "computed_result" if constraint.field == "result" else "audited_result"
        values = [table[tx_id][key] for tx_id in constraint.members]
        if constraint.kind == "sum_equals":
            observed = sum(values)
            equivalent, _ = equivalent_value(observed, constraint.target, constraint.tolerance or ledger.audit_policy.numeric_tolerance)
            output[constraint.constraint_id] = {
                "status": "PASS" if equivalent else "FAIL",
                "observed": observed,
                "target": constraint.target,
                "residual": observed - constraint.target,
            }
        elif constraint.kind == "all_equal":
            expected = constraint.target if constraint.target is not None else values[0]
            status = all(equivalent_value(value, expected, constraint.tolerance or ledger.audit_policy.numeric_tolerance)[0] for value in values)
            output[constraint.constraint_id] = {
                "status": "PASS" if status else "FAIL",
                "observed": values,
                "target": expected,
            }
        else:
            output[constraint.constraint_id] = {"status": "UNSUPPORTED"}
    return output


def compare_representations(ledger: MatrixLedger, run: RunResult) -> dict[str, Any]:
    reference = reference_constraint_audit(ledger, run)
    mismatches: list[dict[str, Any]] = []
    for constraint_id, audit in run.constraint_audits.items():
        ref = reference.get(constraint_id, {})
        if audit.status != ref.get("status"):
            mismatches.append({
                "constraint_id": constraint_id,
                "mmlc_status": audit.status,
                "reference_status": ref.get("status"),
            })
    graph = constraint_factor_graph(ledger)
    return {
        "equivalent": not mismatches,
        "mismatches": mismatches,
        "flat_table_rows": len(ledger.transactions),
        "factor_graph_variable_nodes": len(graph["variables"]),
        "factor_graph_constraint_nodes": len(graph["constraints"]),
        "factor_graph_edges": len(graph["edges"]),
        "factor_graph": graph,
        "reference_audit": reference,
        "interpretation": (
            "A flat table plus custom audit code can reproduce the same checks; "
            "MMLC contributes a typed schema, integrated provenance, cross-axis conflict graph, "
            "and minimum-support repair analysis rather than a new constraint-solving theorem."
        ),
    }
