from pathlib import Path

import pytest

from mmlc.errors import DependencyCycleError
from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_unmarked_cycle_is_rejected():
    ledger = load_ledger(ROOT / "examples" / "dependency_cycle.yaml")
    with pytest.raises(DependencyCycleError):
        Runtime().execute(ledger, deterministic=True)
