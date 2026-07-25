from pathlib import Path

from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_layout_reordering_preserves_semantic_results():
    runtime = Runtime()
    left = runtime.execute(load_ledger(ROOT / "examples" / "four_operations.yaml"), deterministic=True)
    right = runtime.execute(load_ledger(ROOT / "examples" / "reordered_four_operations.yaml"), deterministic=True)
    assert left.global_audit == right.global_audit
    assert {
        k: (v.computed_result, v.status) for k, v in left.transactions.items()
    } == {
        k: (v.computed_result, v.status) for k, v in right.transactions.items()
    }
    assert left.traversals[0]["visited"] != right.traversals[0]["visited"]
    assert left.semantic_hash == right.semantic_hash


def test_semantic_hash_is_reproducible():
    ledger = load_ledger(ROOT / "examples" / "four_operations.yaml")
    runtime = Runtime()
    hashes = {runtime.execute(ledger, deterministic=True).semantic_hash for _ in range(3)}
    assert len(hashes) == 1
