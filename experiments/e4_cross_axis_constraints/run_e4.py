from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmlc.representation import compare_representations
from mmlc.runtime import Runtime
from mmlc.version import __version__
from mmlc.types import (
    AuditPolicy,
    Coordinate,
    MatrixConstraint,
    MatrixLedger,
    Transaction,
)
from mmlc.values import equivalent_value


def build_ledger(
    ledger_id: str,
    clean: list[list[int]],
    observed: list[list[int]],
    *,
    include_blocks: bool,
) -> MatrixLedger:
    rows = len(clean)
    cols = len(clean[0])
    layout = [[f"r{r}c{c}" for c in range(cols)] for r in range(rows)]
    transactions = {
        layout[r][c]: Transaction(
            tx_id=layout[r][c],
            source_id=None,
            base=observed[r][c],
            operator="identity",
            region=f"row-{r}",
        )
        for r in range(rows)
        for c in range(cols)
    }
    constraints: list[MatrixConstraint] = []
    for r in range(rows):
        constraints.append(MatrixConstraint(
            constraint_id=f"row-{r}",
            kind="sum_equals",
            axis="row",
            members=tuple(layout[r]),
            field="result",
            target=sum(clean[r]),
        ))
    for c in range(cols):
        constraints.append(MatrixConstraint(
            constraint_id=f"column-{c}",
            kind="sum_equals",
            axis="column",
            members=tuple(layout[r][c] for r in range(rows)),
            field="result",
            target=sum(clean[r][c] for r in range(rows)),
        ))
    if include_blocks:
        block_rows = 2
        block_cols = 2
        for r0 in range(0, rows, block_rows):
            for c0 in range(0, cols, block_cols):
                members = tuple(
                    layout[r][c]
                    for r in range(r0, min(r0 + block_rows, rows))
                    for c in range(c0, min(c0 + block_cols, cols))
                )
                constraints.append(MatrixConstraint(
                    constraint_id=f"block-{r0}-{c0}",
                    kind="sum_equals",
                    axis="block",
                    members=members,
                    field="result",
                    target=sum(clean[r][c] for r in range(r0, min(r0 + block_rows, rows)) for c in range(c0, min(c0 + block_cols, cols))),
                ))
    coords = {
        layout[r][c]: Coordinate(r, c)
        for r in range(rows)
        for c in range(cols)
    }
    return MatrixLedger(
        ledger_id=ledger_id,
        version="0.4",
        sources={},
        transactions=transactions,
        display_order=[cell for row in layout for cell in row],
        layout=layout,
        coordinates=coords,
        traversals={"execute": "dependency_topological", "display": ["left_to_right", "top_to_bottom"]},
        audit_policy=AuditPolicy(),
        constraints=constraints,
    )


def main() -> None:
    rng = random.Random(20260721)
    runtime = Runtime()
    start = time.perf_counter()

    single_cases = 128
    single_exact = 0
    single_constraint_detection = 0
    single_local_detection = 0
    representation_matches = 0
    single_cross_axis = 0
    supports_searched = 0

    for index in range(single_cases):
        n = 6
        clean = [[rng.randint(1, 30) for _ in range(n)] for _ in range(n)]
        observed = [row[:] for row in clean]
        r = rng.randrange(n)
        c = rng.randrange(n)
        delta = rng.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])
        observed[r][c] += delta
        ledger = build_ledger(f"single-{index}", clean, observed, include_blocks=False)
        run = runtime.execute(ledger, deterministic=True)

        if run.local_failures:
            single_local_detection += 1
        expected_failures = {f"row-{r}", f"column-{c}"}
        if set(run.global_audit["constraint_failures"]) == expected_failures:
            single_constraint_detection += 1
        if any(item["intersection"] == [f"r{r}c{c}"] for item in run.cross_axis_conflicts):
            single_cross_axis += 1
        proposal = run.repair_analysis.proposals[0] if run.repair_analysis.proposals else None
        if (
            run.repair_analysis.status == "SOLVED"
            and run.repair_analysis.minimal_size == 1
            and not run.repair_analysis.ambiguous
            and proposal is not None
            and proposal.cells == (f"r{r}c{c}",)
            and equivalent_value(proposal.corrected_values[f"r{r}c{c}"], clean[r][c])[0]
        ):
            single_exact += 1
        supports_searched += run.repair_analysis.searched_supports
        if compare_representations(ledger, run)["equivalent"]:
            representation_matches += 1

    cancellation_cases = 32
    cancellation_row_hidden = 0
    cancellation_detected = 0
    true_repair_in_proposals = 0
    ambiguity_preserved = 0
    cancellation_representation_matches = 0

    for index in range(cancellation_cases):
        n = 4
        clean = [[rng.randint(1, 30) for _ in range(n)] for _ in range(n)]
        observed = [row[:] for row in clean]
        r = rng.choice([0, 1])
        c_left = rng.choice([0, 1])
        c_right = rng.choice([2, 3])
        delta = rng.choice([1, 2, 3, 4, 5])
        observed[r][c_left] += delta
        observed[r][c_right] -= delta
        ledger = build_ledger(f"cancel-{index}", clean, observed, include_blocks=True)
        run = runtime.execute(ledger, deterministic=True)

        if run.constraint_audits[f"row-{r}"].status == "PASS":
            cancellation_row_hidden += 1
        expected = {f"column-{c_left}", f"column-{c_right}", "block-0-0", "block-0-2"}
        if set(run.global_audit["constraint_failures"]) == expected:
            cancellation_detected += 1
        truth = tuple(sorted((f"r{r}c{c_left}", f"r{r}c{c_right}")))
        proposal_cells = {proposal.cells for proposal in run.repair_analysis.proposals}
        if truth in proposal_cells:
            true_repair_in_proposals += 1
        if run.repair_analysis.ambiguous and len(proposal_cells) >= 2:
            ambiguity_preserved += 1
        if compare_representations(ledger, run)["equivalent"]:
            cancellation_representation_matches += 1

    elapsed = time.perf_counter() - start
    metrics = {
        "runtime_version": __version__,
        "seed": 20260721,
        "single_error": {
            "cases": single_cases,
            "cells_per_case": 36,
            "local_only_detected_cases": single_local_detection,
            "cross_axis_constraint_detected_cases": single_constraint_detection,
            "cross_axis_intersection_localized_cases": single_cross_axis,
            "unique_exact_repair_cases": single_exact,
            "flat_table_reference_equivalent_cases": representation_matches,
            "constraint_detection_accuracy": single_constraint_detection / single_cases,
            "exact_repair_accuracy": single_exact / single_cases,
            "average_supports_searched": supports_searched / single_cases,
        },
        "cancellation": {
            "cases": cancellation_cases,
            "row_total_hidden_cases": cancellation_row_hidden,
            "cross_axis_detected_cases": cancellation_detected,
            "true_repair_in_minimum_proposals": true_repair_in_proposals,
            "ambiguity_preserved_cases": ambiguity_preserved,
            "flat_table_reference_equivalent_cases": cancellation_representation_matches,
            "detection_accuracy": cancellation_detected / cancellation_cases,
            "true_repair_coverage": true_repair_in_proposals / cancellation_cases,
        },
        "representation_comparison": {
            "total_cases": single_cases + cancellation_cases,
            "equivalent_cases": representation_matches + cancellation_representation_matches,
            "equivalence_accuracy": (representation_matches + cancellation_representation_matches) / (single_cases + cancellation_cases),
            "conclusion": "Flat tables with bespoke constraint code reproduce the same arithmetic checks. MMLC standardizes the constraints, factor graph, provenance, conflict intersections and repair proposals in one runtime.",
        },
        "elapsed_seconds": elapsed,
        "cases_per_second": (single_cases + cancellation_cases) / elapsed,
    }

    output = ROOT / "outputs" / "e4_cross_axis_constraints"
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
