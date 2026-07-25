from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

CASES = {
    "correct": ("four_operations.yaml", set()),
    "tampered": ("tampered_multiply.yaml", {"b-mul"}),
    "anti_cancellation": ("anti_cancellation.yaml", {"plus-error", "minus-error"}),
    "division_zero": ("division_by_zero.yaml", {"b-div-zero"}),
}

rows = []
tp = fp = fn = 0
for case_name, (filename, expected_failures) in CASES.items():
    result = Runtime().execute(load_ledger(ROOT / "examples" / filename), deterministic=True)
    observed = set(result.local_failures)
    # Explicit ERROR is also a correctly localized failed transaction.
    observed.update(tx_id for tx_id, tx in result.transactions.items() if tx.status == "ERROR")
    tp += len(observed & expected_failures)
    fp += len(observed - expected_failures)
    fn += len(expected_failures - observed)
    rows.append({
        "case": case_name,
        "expected_failures": sorted(expected_failures),
        "observed_failures": sorted(observed),
        "global_status": result.global_audit["status"],
        "semantic_hash": result.semantic_hash,
    })
precision = tp / (tp + fp) if tp + fp else 1.0
recall = tp / (tp + fn) if tp + fn else 1.0
output = {
    "experiment": "E0 arithmetic executability",
    "cases": rows,
    "audit_precision": precision,
    "audit_recall": recall,
    "pass": precision == 1.0 and recall == 1.0,
}
out_dir = ROOT / "outputs" / "e0_arithmetic"
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "metrics.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(output, ensure_ascii=False, indent=2))
