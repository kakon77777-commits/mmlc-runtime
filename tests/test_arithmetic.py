from fractions import Fraction
from pathlib import Path

from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def run_example(name: str):
    return Runtime().execute(load_ledger(ROOT / "examples" / name), deterministic=True)


def test_four_operations_pass():
    result = run_example("four_operations.yaml")
    assert result.global_audit["status"] == "PASS"
    assert result.local_failures == []
    assert result.transactions["b-div"].computed_result == Fraction(3, 2)


def test_tampered_result_is_localized():
    result = run_example("tampered_multiply.yaml")
    assert result.global_audit["status"] == "FAIL"
    assert result.local_failures == ["b-mul"]
    assert result.transactions["b-mul"].checks["value"].status == "FAIL"


def test_division_by_zero_is_explicit_error():
    result = run_example("division_by_zero.yaml")
    tx = result.transactions["b-div-zero"]
    assert tx.status == "ERROR"
    assert tx.error_type == "DomainError"
