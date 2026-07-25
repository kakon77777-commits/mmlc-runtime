from __future__ import annotations

import json
import random
import sys
import time
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mmlc.runtime import Runtime
from mmlc.types import AuditPolicy, MatrixLedger, SourceObject, Transaction

SEED = 20260721
N = 1024
rng = random.Random(SEED)
operators = ("add", "subtract", "multiply", "divide")

def true_result(op: str, base: int, operand: int):
    if op == "add":
        return base + operand
    if op == "subtract":
        return base - operand
    if op == "multiply":
        return base * operand
    return Fraction(base, operand)

sources = {}
transactions = {}
expected_failures = set()
for i in range(N):
    tx_id = f"tx-{i:04d}"
    source_id = f"source-{i:04d}"
    base = rng.randint(-30, 30)
    operand = rng.randint(-12, 12)
    op = operators[i % len(operators)]
    if op == "divide" and operand == 0:
        operand = 1
    correct = true_result(op, base, operand)
    tampered = i % 2 == 1
    declared = correct
    if tampered:
        target_residual = 1 if (i // 2) % 2 == 0 else -1
        # For divide, I_div = operand * result - base. Choose delta so
        # every tampered transaction contributes exactly ±1 residual.
        delta = Fraction(target_residual, operand) if op == "divide" else target_residual
        declared = correct + delta
        expected_failures.add(tx_id)
    sources[source_id] = SourceObject(source_id, "real", base)
    transactions[tx_id] = Transaction(
        tx_id=tx_id,
        source_id=source_id,
        base=base,
        operator=op,
        operand=operand,
        declared_result=declared,
        region=f"block-{i // 64:02d}",
    )

base_order = list(transactions)
ledger = MatrixLedger(
    ledger_id="randomized-e0-1024",
    version="0.1",
    sources=sources,
    transactions=transactions,
    display_order=base_order,
    traversals={},
    audit_policy=AuditPolicy(numeric_tolerance=1e-12),
)
runtime = Runtime()
start = time.perf_counter()
result = runtime.execute(ledger, deterministic=True)
runtime_seconds = time.perf_counter() - start
observed = set(result.local_failures)
tp = len(observed & expected_failures)
fp = len(observed - expected_failures)
fn = len(expected_failures - observed)
precision = tp / (tp + fp) if tp + fp else 1.0
recall = tp / (tp + fn) if tp + fn else 1.0

# Pure display shuffle must not change semantic hash.
shuffled_order = base_order[:]
rng.shuffle(shuffled_order)
ledger_shuffled = MatrixLedger(
    ledger_id=ledger.ledger_id,
    version=ledger.version,
    sources=sources,
    transactions=transactions,
    display_order=shuffled_order,
    traversals={},
    audit_policy=ledger.audit_policy,
)
shuffled = runtime.execute(ledger_shuffled, deterministic=True)
repeated_hashes = {runtime.execute(ledger, deterministic=True).semantic_hash for _ in range(3)}

metrics = {
    "experiment": "E0 randomized arithmetic stress test",
    "seed": SEED,
    "transactions": N,
    "correct_transactions": N - len(expected_failures),
    "tampered_transactions": len(expected_failures),
    "true_positives": tp,
    "false_positives": fp,
    "false_negatives": fn,
    "audit_precision": precision,
    "audit_recall": recall,
    "runtime_seconds": runtime_seconds,
    "transactions_per_second": N / runtime_seconds,
    "signed_residual_sum": result.global_audit["signed_residual_sum"],
    "absolute_residual_sum": result.global_audit["absolute_residual_sum"],
    "cancellation_detected": result.global_audit["cancellation_detected"],
    "layout_hash_invariant": result.semantic_hash == shuffled.semantic_hash,
    "three_run_reproducibility": len(repeated_hashes) == 1,
    "semantic_hash": result.semantic_hash,
}
metrics["pass"] = all([
    precision == 1.0,
    recall == 1.0,
    metrics["cancellation_detected"],
    metrics["layout_hash_invariant"],
    metrics["three_run_reproducibility"],
])
out_dir = ROOT / "outputs" / "e0_randomized"
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(metrics, ensure_ascii=False, indent=2))
