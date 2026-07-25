from pathlib import Path

from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_signed_errors_cannot_cancel_local_failures():
    result = Runtime().execute(load_ledger(ROOT / "examples" / "anti_cancellation.yaml"), deterministic=True)
    assert result.global_audit["signed_residual_sum"] == 0.0
    assert result.global_audit["absolute_residual_sum"] == 2.0
    assert result.global_audit["cancellation_detected"] is True
    assert set(result.local_failures) == {"plus-error", "minus-error"}
    assert result.global_audit["status"] == "FAIL"
