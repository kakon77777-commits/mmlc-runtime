from __future__ import annotations

import json
import random
import sys
import time
from fractions import Fraction
from pathlib import Path

import sympy as sp

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmlc.exchange import verify_symbolic_numeric_exchange
from mmlc.operators import OperatorSpec, build_default_registry
from mmlc.runtime import Runtime
from mmlc.types import AuditPolicy, EvaluationScenario, MatrixLedger, Transaction
from mmlc.values import free_symbols, is_symbolic


def build_symbolic_ledger(index: int, rng: random.Random) -> MatrixLedger:
    x, y = sp.symbols("x y")
    expressions = [x, y, x + 1, y - 1, x - y, x + y]
    txs: dict[str, Transaction] = {}
    current = sp.Integer(rng.randint(1, 9))
    previous_id: str | None = None
    for j in range(8):
        tx_id = f"L{index:03d}-T{j:02d}"
        op = rng.choice(["add", "subtract", "multiply", "divide"])
        if op == "divide":
            operand = sp.Integer(rng.choice([2, 3, 4, 5]))
        else:
            operand = rng.choice(expressions + [sp.Integer(rng.randint(-4, 6))])
        base = current if previous_id is None else {"ref": previous_id, "field": "result"}
        # ValueRef is created explicitly below to avoid passing parser syntax.
        from mmlc.types import ValueRef
        base = current if previous_id is None else ValueRef(previous_id, "result")
        if op == "add":
            next_value = sp.expand(current + operand)
        elif op == "subtract":
            next_value = sp.expand(current - operand)
        elif op == "multiply":
            next_value = sp.expand(current * operand)
        else:
            next_value = sp.cancel(current / operand)
        txs[tx_id] = Transaction(
            tx_id=tx_id,
            source_id=None,
            base=base,
            operator=op,
            operand=operand,
            declared_result=next_value,
            region="random-symbolic",
        )
        current = next_value
        previous_id = tx_id

    scenario_values = [
        (2, 3),
        (-3, 5),
        (0, 2),
        (Fraction(1, 2), Fraction(3, 2)),
        (Fraction(-2, 3), Fraction(5, 4)),
        (7, -2),
        (1, 1),
        (-5, -3),
    ]
    scenarios = [
        EvaluationScenario(f"S{k:02d}", {"x": xv, "y": yv})
        for k, (xv, yv) in enumerate(scenario_values)
    ]
    return MatrixLedger(
        ledger_id=f"e1-random-{index:03d}",
        version="0.2",
        sources={},
        transactions=txs,
        display_order=list(txs),
        traversals={},
        audit_policy=AuditPolicy(),
        evaluation_scenarios=scenarios,
    )


def negative_control() -> dict[str, object]:
    x = sp.Symbol("x")
    registry = build_default_registry()

    def type_check(base, operand, context):
        return None

    def domain_check(base, operand, context):
        return None

    def evaluator(base, operand, context):
        return len(free_symbols(base))

    registry.register(OperatorSpec(
        "free_symbol_count", "negative-control", 1, evaluator,
        lambda b, a, r, c: r - evaluator(b, a, c), domain_check, type_check,
    ))
    ledger = MatrixLedger(
        ledger_id="e1-negative-control",
        version="0.2",
        sources={},
        transactions={
            "nc": Transaction("nc", None, x, "free_symbol_count", None, None)
        },
        display_order=["nc"],
        traversals={},
        audit_policy=AuditPolicy(),
        evaluation_scenarios=[EvaluationScenario("x-bound", {"x": 2})],
    )
    report = verify_symbolic_numeric_exchange(ledger, runtime=Runtime(registry))
    cell = report.scenario_results[0].cells["nc"]
    return {
        "status": report.status,
        "detected_non_commutation": report.status == "FAIL",
        "symbolic_then_bind": str(cell.substituted_symbolic_value),
        "bind_then_execute": str(cell.direct_numeric_value),
    }


def main() -> None:
    rng = random.Random(20260721)
    start = time.perf_counter()
    ledgers = 128
    total_cells = passed_cells = failed_cells = 0
    failed_ledgers: list[str] = []
    for index in range(ledgers):
        report = verify_symbolic_numeric_exchange(build_symbolic_ledger(index, rng))
        total_cells += report.total_cells
        passed_cells += report.passed_cells
        failed_cells += report.failed_cells
        if report.status != "PASS":
            failed_ledgers.append(report.ledger_id)
    elapsed = time.perf_counter() - start
    negative = negative_control()
    metrics = {
        "experiment": "E1_symbolic_numeric_exchange",
        "seed": 20260721,
        "ledgers": ledgers,
        "transactions_per_ledger": 8,
        "scenarios_per_ledger": 8,
        "total_cell_comparisons": total_cells,
        "passed_cell_comparisons": passed_cells,
        "failed_cell_comparisons": failed_cells,
        "exchange_accuracy": passed_cells / total_cells,
        "failed_ledgers": failed_ledgers,
        "negative_control": negative,
        "elapsed_seconds": elapsed,
        "comparisons_per_second": total_cells / elapsed,
        "status": "PASS" if failed_cells == 0 and negative["detected_non_commutation"] else "FAIL",
    }
    output = ROOT / "outputs" / "e1_symbolic_exchange"
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
