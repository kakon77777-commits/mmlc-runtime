from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmlc.direction import compare_directions
from mmlc.layout import PHYSICAL_TRAVERSALS, build_layout, physical_sequence
from mmlc.runtime import Runtime
from mmlc.types import AuditPolicy, MatrixLedger, MatrixRef, Transaction

SEED = 20260721
DIRECTIONS = ["left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"]


def make_ledger(ledger_id: str, txs: dict[str, Transaction], layout_raw: list[list[str]], execute: str = "dependency_topological") -> MatrixLedger:
    layout, coords, display = build_layout(list(txs), layout_raw)
    return MatrixLedger(
        ledger_id=ledger_id,
        version="0.3",
        sources={},
        transactions=txs,
        display_order=display,
        traversals={"execute": execute, "display": DIRECTIONS},
        audit_policy=AuditPolicy(),
        layout=layout,
        coordinates=coords,
    )


def independent_matrix(index: int, rng: random.Random, size: int = 4) -> MatrixLedger:
    txs: dict[str, Transaction] = {}
    layout: list[list[str]] = []
    for r in range(size):
        row: list[str] = []
        for c in range(size):
            tx_id = f"I{index:03d}-R{r}C{c}"
            value = rng.randint(-100, 100)
            txs[tx_id] = Transaction(tx_id, None, value, "identity", region=f"row-{r}")
            row.append(tx_id)
        layout.append(row)
    return make_ledger(f"e3-independent-{index:03d}", txs, layout)


def directional_scan_matrix(index: int, rng: random.Random, size: int = 4) -> tuple[MatrixLedger, dict[str, int]]:
    txs: dict[str, Transaction] = {}
    layout: list[list[str]] = []
    operands: dict[str, int] = {}
    for r in range(size):
        row: list[str] = []
        for c in range(size):
            tx_id = f"S{index:03d}-R{r}C{c}"
            # Unique positive values make distinct traversal prefixes highly likely
            # while preserving exact integer arithmetic.
            operand = 1 + r * size + c + rng.randint(0, 3) * size * size
            operands[tx_id] = operand
            txs[tx_id] = Transaction(
                tx_id=tx_id,
                source_id=None,
                base=MatrixRef("previous", default=0, has_default=True),
                operator="subtract",
                operand=operand,
                region=f"row-{r}",
            )
            row.append(tx_id)
        layout.append(row)
    return make_ledger(f"e3-scan-{index:03d}", txs, layout, execute="left_to_right"), operands


def spatial_matrix(index: int, rng: random.Random, size: int = 4) -> MatrixLedger:
    txs: dict[str, Transaction] = {}
    layout: list[list[str]] = []
    for r in range(size):
        row: list[str] = []
        for c in range(size):
            tx_id = f"P{index:03d}-R{r}C{c}"
            if c == 0:
                txs[tx_id] = Transaction(tx_id, None, rng.randint(1, 20), "identity", region=f"row-{r}")
            else:
                txs[tx_id] = Transaction(
                    tx_id,
                    None,
                    MatrixRef("left"),
                    "add",
                    rng.randint(1, 20),
                    region=f"row-{r}",
                )
            row.append(tx_id)
        layout.append(row)
    return make_ledger(f"e3-spatial-{index:03d}", txs, layout)


def expected_scan(ledger: MatrixLedger, operands: dict[str, int], direction: str) -> dict[str, int]:
    current = 0
    values: dict[str, int] = {}
    for tx_id in physical_sequence(ledger, direction):
        current -= operands[tx_id]
        values[tx_id] = current
    return values


def routing_benchmark(size: int = 32, trials: int = 1024) -> dict[str, float | int]:
    rng = random.Random(SEED + 9)
    txs: dict[str, Transaction] = {}
    layout_raw: list[list[str]] = []
    for r in range(size):
        row = []
        for c in range(size):
            tx_id = f"Q-R{r:02d}C{c:02d}"
            txs[tx_id] = Transaction(tx_id, None, 0, "identity", region=f"row-{r}")
            row.append(tx_id)
        layout_raw.append(row)
    row_ledger = make_ledger("e3-routing-rows", txs, layout_raw)

    # A second ledger carries column region metadata. The numerical grid is the
    # same; only the query-facing region index changes.
    column_txs = {
        tx_id: Transaction(tx.tx_id, tx.source_id, tx.base, tx.operator, tx.operand, tx.declared_result, region=f"col-{row_ledger.coordinates[tx_id].column}")
        for tx_id, tx in txs.items()
    }
    col_ledger = make_ledger("e3-routing-cols", column_txs, layout_raw)
    row_major = physical_sequence(row_ledger, "left_to_right")
    row_rank = {tx_id: i for i, tx_id in enumerate(row_major)}

    fixed_visits = 0
    mmr_visits = 0
    row_queries = 0
    col_queries = 0
    for _ in range(trials):
        if rng.random() < 0.5:
            r = rng.randrange(size)
            targets = [row_ledger.layout[r][c] for c in range(size)]
            explicit = physical_sequence(row_ledger, "left_to_right", region=f"row-{r}")
            row_queries += 1
        else:
            c = rng.randrange(size)
            targets = [col_ledger.layout[r][c] for r in range(size)]
            explicit = physical_sequence(col_ledger, "top_to_bottom", region=f"col-{c}")
            col_queries += 1
        fixed_visits += max(row_rank[tx_id] for tx_id in targets if tx_id is not None) + 1
        mmr_visits += len(explicit)
    return {
        "grid_size": size,
        "trials": trials,
        "row_queries": row_queries,
        "column_queries": col_queries,
        "fixed_row_major_visits": fixed_visits,
        "explicit_mmr_visits": mmr_visits,
        "mean_fixed_visits": fixed_visits / trials,
        "mean_mmr_visits": mmr_visits / trials,
        "visit_reduction": 1.0 - mmr_visits / fixed_visits,
        "assumption": "query supplies the target row/column region; route selection is not learned",
    }


def main() -> None:
    rng = random.Random(SEED)
    engine = Runtime()
    start = time.perf_counter()

    neutral_ledgers = 64
    neutral_failures = 0
    neutral_execution_hash_classes: list[int] = []
    for i in range(neutral_ledgers):
        comparison = compare_directions(independent_matrix(i, rng), runtime=engine)
        if comparison.direction_sensitive:
            neutral_failures += 1
        neutral_execution_hash_classes.append(len({run.execution_hash for run in comparison.runs.values()}))

    scan_ledgers = 128
    scan_cells = 0
    scan_value_errors = 0
    scan_direction_sensitive = 0
    scan_semantic_classes: list[int] = []
    for i in range(scan_ledgers):
        ledger, operands = directional_scan_matrix(i, rng)
        comparison = compare_directions(ledger, runtime=engine)
        if comparison.direction_sensitive:
            scan_direction_sensitive += 1
        scan_semantic_classes.append(len(comparison.semantic_equivalence_classes))
        for direction, run in comparison.runs.items():
            expected = expected_scan(ledger, operands, direction)
            for tx_id, value in expected.items():
                scan_cells += 1
                if run.transactions[tx_id].computed_result != value:
                    scan_value_errors += 1

    spatial_ledgers = 64
    spatial_failures = 0
    for i in range(spatial_ledgers):
        comparison = compare_directions(spatial_matrix(i, rng), runtime=engine)
        if comparison.direction_sensitive:
            spatial_failures += 1

    routing = routing_benchmark()
    elapsed = time.perf_counter() - start
    metrics = {
        "experiment": "E3 matrix layout and multidirectional execution",
        "seed": SEED,
        "physical_traversals": list(PHYSICAL_TRAVERSALS),
        "direction_neutral": {
            "ledgers": neutral_ledgers,
            "semantic_failures": neutral_failures,
            "semantic_invariance_accuracy": 1.0 - neutral_failures / neutral_ledgers,
            "mean_execution_hash_classes": sum(neutral_execution_hash_classes) / len(neutral_execution_hash_classes),
        },
        "direction_sensitive_scan": {
            "ledgers": scan_ledgers,
            "cell_comparisons": scan_cells,
            "value_errors": scan_value_errors,
            "value_accuracy": 1.0 - scan_value_errors / scan_cells,
            "direction_sensitive_ledgers": scan_direction_sensitive,
            "direction_sensitivity_rate": scan_direction_sensitive / scan_ledgers,
            "mean_semantic_classes": sum(scan_semantic_classes) / len(scan_semantic_classes),
        },
        "spatial_reference": {
            "ledgers": spatial_ledgers,
            "directional_semantic_failures": spatial_failures,
            "direction_invariance_accuracy": 1.0 - spatial_failures / spatial_ledgers,
        },
        "routing_benchmark": routing,
        "runtime_seconds": elapsed,
    }
    metrics["pass"] = all([
        neutral_failures == 0,
        scan_value_errors == 0,
        scan_direction_sensitive == scan_ledgers,
        spatial_failures == 0,
        routing["visit_reduction"] > 0,
    ])

    output = ROOT / "outputs" / "e3_matrix_directions"
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if not metrics["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
