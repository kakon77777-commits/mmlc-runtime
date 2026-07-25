from pathlib import Path

import pytest

from mmlc.direction import compare_directions
from mmlc.errors import MissingReferenceError, TraversalSemanticError
from mmlc.layout import physical_sequence
from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_true_2d_physical_traversals():
    ledger = load_ledger(ROOT / "examples" / "matrix_layout_2d.yaml")
    assert physical_sequence(ledger, "left_to_right") == ["a", "b", "c", "d", "e", "f"]
    assert physical_sequence(ledger, "right_to_left") == ["c", "b", "a", "f", "e", "d"]
    assert physical_sequence(ledger, "top_to_bottom") == ["a", "d", "b", "e", "c", "f"]
    assert physical_sequence(ledger, "bottom_to_top") == ["d", "a", "e", "b", "f", "c"]


def test_sparse_layout_skips_empty_cells():
    ledger = load_ledger(ROOT / "examples" / "sparse_layout.yaml")
    assert physical_sequence(ledger, "left_to_right") == ["a", "b", "c", "d"]
    assert physical_sequence(ledger, "top_to_bottom") == ["a", "c", "b", "d"]


def test_independent_matrix_is_semantically_direction_neutral():
    ledger = load_ledger(ROOT / "examples" / "matrix_layout_2d.yaml")
    comparison = compare_directions(ledger)
    assert comparison.direction_sensitive is False
    assert comparison.semantic_equivalence_classes == [[
        "bottom_to_top", "left_to_right", "right_to_left", "top_to_bottom"
    ]]
    assert len({run.execution_hash for run in comparison.runs.values()}) == 4


def test_previous_reference_is_direction_sensitive():
    ledger = load_ledger(ROOT / "examples" / "directional_previous_scan.yaml")
    comparison = compare_directions(ledger, ["left_to_right", "right_to_left"])
    assert comparison.direction_sensitive is True
    left = comparison.runs["left_to_right"]
    right = comparison.runs["right_to_left"]
    assert left.execution_order == ["n1", "n2", "n3", "n4"]
    assert right.execution_order == ["n4", "n3", "n2", "n1"]
    assert [left.transactions[x].computed_result for x in ["n1", "n2", "n3", "n4"]] == [-1, -3, -6, -10]
    assert [right.transactions[x].computed_result for x in ["n1", "n2", "n3", "n4"]] == [-10, -9, -7, -4]
    assert left.semantic_hash != right.semantic_hash


def test_spatial_reference_is_coordinate_semantic_not_scan_order_semantic():
    ledger = load_ledger(ROOT / "examples" / "spatial_left_chain.yaml")
    comparison = compare_directions(ledger)
    assert comparison.direction_sensitive is False
    for run in comparison.runs.values():
        assert {tx_id: tx.computed_result for tx_id, tx in run.transactions.items()} == {
            "a": 1, "b": 3, "c": 6, "d": 10, "e": 30, "f": 60
        }


def test_missing_spatial_neighbour_without_default_is_explicit_error():
    ledger = load_ledger(ROOT / "examples" / "missing_neighbour.yaml")
    with pytest.raises(MissingReferenceError):
        Runtime().execute(ledger, deterministic=True)


def test_previous_reference_rejects_graph_only_execution():
    ledger = load_ledger(ROOT / "examples" / "directional_previous_scan.yaml")
    with pytest.raises(TraversalSemanticError):
        Runtime().execute(ledger, deterministic=True, execution_traversal="dependency_topological")


def test_traversal_logs_include_coordinates_and_path_metrics():
    ledger = load_ledger(ROOT / "examples" / "matrix_layout_2d.yaml")
    result = Runtime().execute(ledger, deterministic=True, execution_traversal="top_to_bottom")
    top = next(item for item in result.traversals if item["traversal"] == "top_to_bottom")
    assert top["role"] == "execute"
    assert top["coordinates"]["e"] == {"row": 1, "column": 1}
    assert top["metrics"]["visit_count"] == 6
    assert top["metrics"]["manhattan_distance"] > 0
