from pathlib import Path

import sympy as sp

from mmlc.dependency import ancestors, build_dependencies
from mmlc.parser import load_ledger
from mmlc.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def test_symbolic_invariants_pass():
    result = Runtime().execute(load_ledger(ROOT / "examples" / "symbolic_x.yaml"), deterministic=True)
    assert result.global_audit["status"] == "PASS"
    assert sp.simplify(result.transactions["s-div"].computed_result - 3 / sp.Symbol("x")) == 0


def test_dependency_chain_executes_topologically_and_traces():
    ledger = load_ledger(ROOT / "examples" / "dependency_chain.yaml")
    result = Runtime().execute(ledger, deterministic=True)
    assert result.execution_order == ["t1", "t2", "t3"]
    assert result.transactions["t3"].computed_result == 11
    deps = build_dependencies(ledger)
    assert ancestors("t3", deps) == ["t1", "t2"]
