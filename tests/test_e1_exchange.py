from pathlib import Path

from mmlc.exchange import verify_symbolic_numeric_exchange
from mmlc.parser import load_ledger

ROOT = Path(__file__).resolve().parents[1]


def test_symbolic_numeric_exchange_commutes_for_all_scenarios():
    ledger = load_ledger(ROOT / "examples" / "symbolic_exchange.yaml")
    report = verify_symbolic_numeric_exchange(ledger)
    assert report.status == "PASS"
    assert report.total_cells == 12
    assert report.passed_cells == 12
    assert report.failed_cells == 0
    assert all(s.status == "PASS" for s in report.scenario_results)
