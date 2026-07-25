"""Small reproducible release benchmarks for Runtime 1.x.

These benchmarks measure implementation overhead on one machine. They are not
claims of superiority over spreadsheets, DAG engines, numerical solvers, or
probabilistic programming systems.
"""

from __future__ import annotations

import platform
import statistics
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .persistence import semantic_hash
from .runtime import Runtime
from .types import AuditPolicy, MatrixLedger, Transaction, ValueRef
from .version import __version__


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    size: int
    repeats: int
    durations_seconds: tuple[float, ...]
    median_seconds: float
    min_seconds: float
    max_seconds: float
    throughput_per_second: float
    peak_memory_bytes: int
    deterministic_hash: str
    hashes_identical: bool
    global_status: str


def _independent_ledger(size: int) -> MatrixLedger:
    transactions = {
        f"t{i:05d}": Transaction(
            tx_id=f"t{i:05d}",
            source_id=None,
            base=i,
            operator="add",
            operand=1,
            declared_result=i + 1,
            region="benchmark",
        )
        for i in range(size)
    }
    order = list(transactions)
    return MatrixLedger(
        ledger_id=f"benchmark-independent-{size}",
        version="1.0",
        sources={},
        transactions=transactions,
        display_order=order,
        layout=[order],
        traversals={"display": "left_to_right", "execute": "dependency_topological"},
        audit_policy=AuditPolicy(),
    )


def _chain_ledger(size: int) -> MatrixLedger:
    transactions: dict[str, Transaction] = {}
    for i in range(size):
        tx_id = f"t{i:05d}"
        if i == 0:
            base: Any = 0
            dependencies: list[str] = []
        else:
            parent = f"t{i - 1:05d}"
            base = ValueRef(parent)
            dependencies = [parent]
        transactions[tx_id] = Transaction(
            tx_id=tx_id,
            source_id=None,
            base=base,
            operator="add",
            operand=1,
            declared_result=i + 1,
            dependencies=dependencies,
            region="benchmark",
        )
    order = list(transactions)
    return MatrixLedger(
        ledger_id=f"benchmark-chain-{size}",
        version="1.0",
        sources={},
        transactions=transactions,
        display_order=order,
        layout=[order],
        traversals={"display": "left_to_right", "execute": "dependency_topological"},
        audit_policy=AuditPolicy(),
    )


def _run_case(name: str, size: int, repeats: int, factory: Any) -> BenchmarkCase:
    durations: list[float] = []
    hashes: list[str] = []
    peak = 0
    status = "UNKNOWN"
    runtime = Runtime()
    for _ in range(repeats):
        ledger = factory(size)
        tracemalloc.start()
        started = time.perf_counter()
        result = runtime.execute(ledger, deterministic=True)
        elapsed = time.perf_counter() - started
        _, observed_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        durations.append(elapsed)
        peak = max(peak, observed_peak)
        hashes.append(result.semantic_hash)
        status = str(result.global_audit.get("status", "UNKNOWN"))
    median = statistics.median(durations)
    return BenchmarkCase(
        name=name,
        size=size,
        repeats=repeats,
        durations_seconds=tuple(durations),
        median_seconds=median,
        min_seconds=min(durations),
        max_seconds=max(durations),
        throughput_per_second=(size / median) if median > 0 else float("inf"),
        peak_memory_bytes=peak,
        deterministic_hash=hashes[0],
        hashes_identical=len(set(hashes)) == 1,
        global_status=status,
    )


def run_release_benchmarks(
    *, sizes: Iterable[int] = (64, 256, 1024), repeats: int = 3
) -> dict[str, Any]:
    normalized_sizes = tuple(int(size) for size in sizes)
    if not normalized_sizes or any(size < 1 for size in normalized_sizes):
        raise ValueError("Benchmark sizes must be positive integers")
    if repeats < 1:
        raise ValueError("Benchmark repeats must be positive")
    cases: list[BenchmarkCase] = []
    for size in normalized_sizes:
        cases.append(_run_case("independent", size, repeats, _independent_ledger))
        cases.append(_run_case("dependency_chain", size, repeats, _chain_ledger))
    payload = {
        "benchmark_format": "MMLC-RELEASE-BENCHMARK v1",
        "runtime_version": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "sizes": list(normalized_sizes),
        "repeats": repeats,
        "cases": [asdict(case) for case in cases],
        "interpretation": (
            "Single-machine implementation measurements only; no comparison or superiority claim. "
            "tracemalloc is enabled and affects absolute timing."
        ),
    }
    payload["benchmark_hash"] = semantic_hash(payload)
    return payload
