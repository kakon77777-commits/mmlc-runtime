from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmlc.dependency import ancestors, descendants
from mmlc.runtime import Runtime
from mmlc.types import AuditPolicy, MatrixLedger, Transaction, ValueRef


def build_dag(index: int, rng: random.Random, n: int = 64) -> tuple[MatrixLedger, set[str]]:
    txs: dict[str, Transaction] = {}
    audited_values: dict[str, int] = {}
    source_count = 8
    roots = {f"G{index:03d}-T{i:02d}" for i in rng.sample(range(source_count), 3)}
    for i in range(n):
        tx_id = f"G{index:03d}-T{i:02d}"
        if i < source_count:
            base = rng.randint(1, 20)
            operand = rng.randint(-5, 8)
            clean = base + operand
        else:
            parent_count = 1 if rng.random() < 0.7 else 2
            parents = sorted(rng.sample(range(i), parent_count))
            p1 = f"G{index:03d}-T{parents[0]:02d}"
            base = ValueRef(p1, "audited_result")
            if parent_count == 1:
                operand = rng.randint(-4, 7)
                clean = audited_values[p1] + operand
            else:
                p2 = f"G{index:03d}-T{parents[1]:02d}"
                operand = ValueRef(p2, "audited_result")
                clean = audited_values[p1] + audited_values[p2]
        expected = clean + 1 if tx_id in roots else clean
        audited_values[tx_id] = expected
        txs[tx_id] = Transaction(
            tx_id=tx_id,
            source_id=None,
            base=base,
            operator="add",
            operand=operand,
            declared_result=expected,
            region="dag",
        )
    ledger = MatrixLedger(
        ledger_id=f"e2-random-dag-{index:03d}",
        version="0.2",
        sources={},
        transactions=txs,
        display_order=list(txs),
        traversals={},
        audit_policy=AuditPolicy(),
    )
    return ledger, roots


def main() -> None:
    rng = random.Random(20260721)
    engine = Runtime()
    graphs = 128
    nodes_per_graph = 64
    start = time.perf_counter()
    root_tp = root_fp = root_fn = 0
    taint_tp = taint_fp = taint_fn = 0
    path_failures = 0
    naive_root_count = 0
    actual_root_count = 0

    for index in range(graphs):
        ledger, expected_roots = build_dag(index, rng, nodes_per_graph)
        result = engine.execute(ledger, deterministic=True)
        predicted_roots = set(result.root_cause_analysis["root_causes"])
        root_tp += len(predicted_roots & expected_roots)
        root_fp += len(predicted_roots - expected_roots)
        root_fn += len(expected_roots - predicted_roots)
        actual_root_count += len(expected_roots)

        deps = {tx_id: set(r.dependencies) for tx_id, r in result.transactions.items()}
        expected_tainted: set[str] = set()
        for root in expected_roots:
            expected_tainted.update(descendants(root, deps))
        expected_tainted -= expected_roots
        predicted_tainted = set(result.tainted_transactions)
        taint_tp += len(predicted_tainted & expected_tainted)
        taint_fp += len(predicted_tainted - expected_tainted)
        taint_fn += len(expected_tainted - predicted_tainted)
        naive_root_count += len(set(result.local_failures) | set(result.tainted_transactions))

        for tx_id in predicted_tainted:
            expected_for_node = sorted(root for root in expected_roots if root in ancestors(tx_id, deps))
            if result.transactions[tx_id].root_causes != expected_for_node:
                path_failures += 1

    elapsed = time.perf_counter() - start
    root_precision = root_tp / max(root_tp + root_fp, 1)
    root_recall = root_tp / max(root_tp + root_fn, 1)
    taint_precision = taint_tp / max(taint_tp + taint_fp, 1)
    taint_recall = taint_tp / max(taint_tp + taint_fn, 1)
    metrics = {
        "experiment": "E2_dependency_root_cause",
        "seed": 20260721,
        "graphs": graphs,
        "nodes_per_graph": nodes_per_graph,
        "total_transactions": graphs * nodes_per_graph,
        "actual_root_count": actual_root_count,
        "predicted_root_true_positives": root_tp,
        "predicted_root_false_positives": root_fp,
        "predicted_root_false_negatives": root_fn,
        "root_precision": root_precision,
        "root_recall": root_recall,
        "taint_true_positives": taint_tp,
        "taint_false_positives": taint_fp,
        "taint_false_negatives": taint_fn,
        "taint_precision": taint_precision,
        "taint_recall": taint_recall,
        "root_path_assignment_failures": path_failures,
        "naive_nonpass_as_root_count": naive_root_count,
        "root_count_reduction_ratio": 1.0 - actual_root_count / max(naive_root_count, 1),
        "elapsed_seconds": elapsed,
        "transactions_per_second": graphs * nodes_per_graph / elapsed,
        "status": "PASS" if root_fp == root_fn == taint_fp == taint_fn == path_failures == 0 else "FAIL",
    }
    output = ROOT / "outputs" / "e2_root_cause"
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
