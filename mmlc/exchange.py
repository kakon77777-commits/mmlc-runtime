from __future__ import annotations

from .persistence import semantic_hash
from .runtime import Runtime
from .transform import instantiate_ledger
from .types import (
    EvaluationScenario,
    ExchangeCellResult,
    ExchangeReport,
    ExchangeScenarioResult,
    MatrixLedger,
)
from .values import equivalent_value, substitute_value
from .version import __version__


def verify_symbolic_numeric_exchange(
    ledger: MatrixLedger,
    *,
    runtime: Runtime | None = None,
    scenarios: list[EvaluationScenario] | None = None,
    tolerance: float | None = None,
) -> ExchangeReport:
    """Verify Eval(execute(symbolic ledger)) == execute(Eval(ledger))."""
    engine = runtime or Runtime()
    chosen = scenarios if scenarios is not None else ledger.evaluation_scenarios
    if not chosen:
        raise ValueError("No evaluation scenarios were provided")
    tol = ledger.audit_policy.numeric_tolerance if tolerance is None else tolerance
    symbolic_run = engine.execute(ledger, deterministic=True)

    scenario_results: list[ExchangeScenarioResult] = []
    total = passed = failed = 0
    for scenario in chosen:
        bound = instantiate_ledger(ledger, scenario.bindings, ledger_id_suffix=scenario.scenario_id)
        numeric_run = engine.execute(bound, deterministic=True)
        cells: dict[str, ExchangeCellResult] = {}
        for tx_id in symbolic_run.execution_order:
            total += 1
            symbolic_value = symbolic_run.transactions[tx_id].computed_result
            substituted = substitute_value(symbolic_value, scenario.bindings)
            direct = numeric_run.transactions[tx_id].computed_result
            equivalent, detail = equivalent_value(substituted, direct, tolerance=tol)
            if equivalent:
                passed += 1
            else:
                failed += 1
            cells[tx_id] = ExchangeCellResult(
                tx_id=tx_id,
                symbolic_value=symbolic_value,
                substituted_symbolic_value=substituted,
                direct_numeric_value=direct,
                equivalent=equivalent,
                detail=detail,
            )
        scenario_status = "PASS" if all(cell.equivalent for cell in cells.values()) else "FAIL"
        scenario_results.append(
            ExchangeScenarioResult(
                scenario_id=scenario.scenario_id,
                bindings=dict(scenario.bindings),
                status=scenario_status,
                cells=cells,
                symbolic_hash=semantic_hash({k: v.computed_result for k, v in symbolic_run.transactions.items()}),
                numeric_hash=semantic_hash({k: v.computed_result for k, v in numeric_run.transactions.items()}),
            )
        )
    return ExchangeReport(
        ledger_id=ledger.ledger_id,
        runtime_version=__version__,
        status="PASS" if failed == 0 else "FAIL",
        scenario_results=scenario_results,
        total_cells=total,
        passed_cells=passed,
        failed_cells=failed,
    )
