from __future__ import annotations

from collections import defaultdict
from typing import Any

import sympy as sp

from .types import CheckResult, MatrixLedger, Transaction, TransactionResult
from .values import exact_equal, is_symbolic, numeric_abs


def _pass(detail: str = "") -> CheckResult:
    return CheckResult("PASS", detail)


def _fail(detail: str, residual: Any = None, scaled: float | None = None) -> CheckResult:
    return CheckResult("FAIL", detail, residual=residual, scaled_residual=scaled)


def source_check(ledger: MatrixLedger, tx: Transaction, resolved_base: Any) -> CheckResult:
    if tx.source_id is None:
        return _pass("No shared source claimed")
    source = ledger.sources.get(tx.source_id)
    if source is None:
        return _fail(f"Missing source object: {tx.source_id}")
    if exact_equal(source.value, resolved_base):
        return _pass(f"Matches source {tx.source_id}")
    return _fail(f"Base does not match source {tx.source_id}")


def dependency_declaration_check(tx: Transaction, known_ids: set[str]) -> CheckResult:
    missing = [dep for dep in tx.dependencies if dep not in known_ids]
    if missing:
        return _fail(f"Missing dependencies: {missing}")
    return _pass("Dependency declarations resolve")


def dependency_health_check(unhealthy_dependencies: list[str]) -> CheckResult:
    if unhealthy_dependencies:
        return _fail(f"Unhealthy upstream transactions: {unhealthy_dependencies}")
    return _pass("All upstream transactions are healthy")


def value_check(
    residual: Any,
    base: Any,
    operand: Any,
    audited_result: Any,
    tolerance: float,
) -> CheckResult:
    if is_symbolic(residual):
        simplified = sp.simplify(residual)
        if simplified == 0:
            return _pass("Exact symbolic invariant")
        if simplified.free_symbols:
            return _fail("Symbolic residual is nonzero", residual=simplified)
        abs_res = abs(float(simplified.evalf()))
    else:
        try:
            abs_res = numeric_abs(residual)
        except Exception:
            return _fail("Residual is not numerically comparable", residual=residual)

    scale = 1.0
    for value in (base, operand, audited_result):
        try:
            if value is not None and not isinstance(value, dict):
                scale += numeric_abs(value)
        except Exception:
            continue
    scaled = abs_res / scale
    if scaled <= tolerance:
        return _pass(f"Scaled residual {scaled:.3e} <= {tolerance:.3e}")
    return _fail(
        f"Scaled residual {scaled:.3e} > {tolerance:.3e}",
        residual=residual,
        scaled=scaled,
    )


def aggregate_audits(
    ledger: MatrixLedger,
    results: dict[str, TransactionResult],
) -> tuple[list[str], list[str], dict[str, dict[str, Any]], dict[str, Any]]:
    local_failures = sorted(tx_id for tx_id, result in results.items() if result.local_status != "PASS")
    tainted = sorted(tx_id for tx_id, result in results.items() if result.status == "TAINTED")
    unhealthy = sorted(set(local_failures) | set(tainted))
    regions: dict[str, list[str]] = defaultdict(list)
    for tx_id, tx in ledger.transactions.items():
        regions[tx.region].append(tx_id)

    region_audits: dict[str, dict[str, Any]] = {}
    signed_global = 0.0
    absolute_global = 0.0
    numeric_count = 0
    for region, tx_ids in sorted(regions.items()):
        region_local_failures = sorted(tx_id for tx_id in tx_ids if tx_id in local_failures)
        region_tainted = sorted(tx_id for tx_id in tx_ids if tx_id in tainted)
        region_abs = 0.0
        region_signed = 0.0
        for tx_id in tx_ids:
            check = results[tx_id].checks.get("value")
            if not check or check.residual is None:
                continue
            try:
                value = float(check.residual)
            except Exception:
                continue
            region_signed += value
            region_abs += abs(value)
            signed_global += value
            absolute_global += abs(value)
            numeric_count += 1
        if region_local_failures:
            status = "FAIL"
        elif region_tainted:
            status = "TAINTED"
        else:
            status = "PASS"
        region_audits[region] = {
            "status": status,
            "local_failures": region_local_failures,
            "tainted_transactions": region_tainted,
            "signed_residual_sum": region_signed,
            "absolute_residual_sum": region_abs,
        }

    if local_failures:
        global_status = "FAIL"
    elif tainted:
        global_status = "TAINTED"
    else:
        global_status = "PASS"
    global_audit = {
        "status": global_status,
        "local_failures": local_failures,
        "tainted_transactions": tainted,
        "unhealthy_transactions": unhealthy,
        "signed_residual_sum": signed_global,
        "absolute_residual_sum": absolute_global,
        "numeric_residual_count": numeric_count,
        "cancellation_detected": bool(local_failures and abs(signed_global) <= ledger.audit_policy.numeric_tolerance and absolute_global > ledger.audit_policy.numeric_tolerance),
        "local_failures_preserved": True,
        "taint_propagation_enabled": True,
    }
    return local_failures, tainted, region_audits, global_audit
