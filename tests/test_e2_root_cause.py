from pathlib import Path

from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_single_root_taints_descendants_without_relabeling_them_as_roots():
    result = Runtime().execute(load_ledger(ROOT / "examples" / "root_cause_chain.yaml"), deterministic=True)
    assert result.local_failures == ["origin"]
    assert result.tainted_transactions == ["derived-1", "derived-2"]
    assert result.transactions["origin"].status == "FAIL"
    assert result.transactions["derived-1"].local_status == "PASS"
    assert result.transactions["derived-1"].status == "TAINTED"
    assert result.transactions["derived-2"].root_causes == ["origin"]
    assert result.transactions["healthy-side"].status == "PASS"
    assert result.root_cause_analysis["per_transaction"]["derived-2"]["paths"]["origin"] == [
        "origin", "derived-1", "derived-2"
    ]


def test_two_independent_roots_are_preserved_at_merge():
    result = Runtime().execute(load_ledger(ROOT / "examples" / "root_cause_merge.yaml"), deterministic=True)
    assert result.root_cause_analysis["root_causes"] == ["root-a", "root-b"]
    assert result.transactions["merge"].status == "TAINTED"
    assert result.transactions["merge"].root_causes == ["root-a", "root-b"]


def test_taint_is_field_sensitive_between_computed_and_declared_channels():
    result = Runtime().execute(load_ledger(ROOT / "examples" / "field_sensitive_taint.yaml"), deterministic=True)
    assert result.transactions["origin"].status == "FAIL"
    assert result.transactions["computed-channel"].status == "PASS"
    assert result.transactions["computed-channel"].root_causes == []
    assert result.transactions["declared-channel"].status == "TAINTED"
    assert result.transactions["declared-channel"].root_causes == ["origin"]
