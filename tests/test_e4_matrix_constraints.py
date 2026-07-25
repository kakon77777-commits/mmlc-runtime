from pathlib import Path

import sympy as sp

from mmlc.parser import load_ledger
from mmlc.representation import compare_representations, constraint_factor_graph
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_constraint_scopes_compile_to_expected_members():
    ledger = load_ledger(ROOT / "examples" / "cross_axis_single_error.yaml")
    by_id = {item.constraint_id: item for item in ledger.constraints}
    assert by_id["row-1"].axis == "row"
    assert by_id["row-1"].members == ("r1c0", "r1c1", "r1c2")
    assert by_id["column-1"].axis == "column"
    assert by_id["column-1"].members == ("r0c1", "r1c1", "r2c1")


def test_cross_axis_failure_localizes_single_cell_without_local_transaction_failure():
    ledger = load_ledger(ROOT / "examples" / "cross_axis_single_error.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    assert result.local_failures == []
    assert result.global_audit["constraint_failures"] == ["column-1", "row-1"]
    assert result.global_audit["status"] == "FAIL"
    assert result.cross_axis_conflicts == [{
        "constraints": ["column-1", "row-1"],
        "axes": ["column", "row"],
        "intersection": ["r1c1"],
    }]
    repair = result.repair_analysis
    assert repair.status == "SOLVED"
    assert repair.minimal_size == 1
    assert repair.ambiguous is False
    assert repair.proposals[0].cells == ("r1c1",)
    assert sp.simplify(repair.proposals[0].deltas["r1c1"] + 3) == 0
    assert sp.simplify(repair.proposals[0].corrected_values["r1c1"] - 5) == 0


def test_cross_axis_constraints_detect_cancellation_hidden_from_row_total():
    ledger = load_ledger(ROOT / "examples" / "cross_axis_cancellation.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    assert result.constraint_audits["row-0"].status == "PASS"
    assert set(result.global_audit["constraint_failures"]) == {
        "column-0", "column-3", "block-tl", "block-tr"
    }
    assert result.repair_analysis.minimal_size == 2
    assert result.repair_analysis.ambiguous is True
    proposals = {proposal.cells for proposal in result.repair_analysis.proposals}
    assert ("r0c0", "r0c3") in proposals


def test_ambiguous_minimum_repair_is_preserved_not_forced_unique():
    ledger = load_ledger(ROOT / "examples" / "ambiguous_row_repair.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    repair = result.repair_analysis
    assert repair.status == "SOLVED"
    assert repair.minimal_size == 1
    assert repair.ambiguous is True
    assert {proposal.cells for proposal in repair.proposals} == {("a",), ("b",), ("c",)}


def test_clean_constraints_need_no_repair():
    ledger = load_ledger(ROOT / "examples" / "constraint_clean.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    assert result.global_audit["status"] == "PASS"
    assert result.global_audit["constraint_failures"] == []
    assert result.repair_analysis.status == "NOT_NEEDED"
    assert result.repair_analysis.minimal_size == 0


def test_flat_table_reference_and_factor_graph_are_equivalent():
    ledger = load_ledger(ROOT / "examples" / "cross_axis_single_error.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    comparison = compare_representations(ledger, result)
    assert comparison["equivalent"] is True
    assert comparison["mismatches"] == []
    graph = constraint_factor_graph(ledger)
    assert len(graph["variables"]) == 9
    assert len(graph["constraints"]) == 6
    assert len(graph["edges"]) == 18


def test_all_equal_constraint_is_audited_but_not_claimed_as_linear_repair():
    ledger = load_ledger(ROOT / "examples" / "all_equal_column.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    assert result.constraint_audits["same-base"].status == "FAIL"
    assert result.constraint_audits["same-base"].residual == 1
    assert result.repair_analysis.status == "UNSUPPORTED"
    assert result.repair_analysis.exact is False
