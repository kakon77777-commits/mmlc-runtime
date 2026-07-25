from __future__ import annotations

from typing import Iterable

from .errors import LayoutError, TraversalError
from .types import Coordinate, MatrixLedger

PHYSICAL_TRAVERSALS = (
    "left_to_right",
    "right_to_left",
    "top_to_bottom",
    "bottom_to_top",
    "snake_horizontal",
    "snake_vertical",
)


def build_layout(
    tx_ids: list[str],
    raw_layout: object,
) -> tuple[list[list[str | None]], dict[str, Coordinate], list[str]]:
    """Normalize a possibly sparse rectangular layout.

    Missing layout defaults to a single horizontal row for backwards
    compatibility. Explicit layouts may contain ``null`` empty cells, but every
    transaction must occur exactly once.
    """
    if raw_layout is None:
        layout: list[list[str | None]] = [list(tx_ids)]
    elif not isinstance(raw_layout, list) or not raw_layout:
        raise LayoutError("layout must be a non-empty list of rows")
    else:
        layout = []
        for row in raw_layout:
            if not isinstance(row, list):
                raise LayoutError("each layout row must be a list")
            layout.append([None if cell is None else str(cell) for cell in row])

    width = max((len(row) for row in layout), default=0)
    if width == 0:
        raise LayoutError("layout cannot be empty")
    layout = [row + [None] * (width - len(row)) for row in layout]

    flattened = [cell for row in layout for cell in row if cell is not None]
    if len(flattened) != len(set(flattened)):
        raise LayoutError("layout contains duplicate transaction IDs")
    if set(flattened) != set(tx_ids):
        missing = sorted(set(tx_ids) - set(flattened))
        unknown = sorted(set(flattened) - set(tx_ids))
        raise LayoutError(f"layout must contain every transaction exactly once; missing={missing}, unknown={unknown}")

    coordinates: dict[str, Coordinate] = {}
    for r, row in enumerate(layout):
        for c, tx_id in enumerate(row):
            if tx_id is not None:
                coordinates[tx_id] = Coordinate(r, c)
    display_order = [cell for row in layout for cell in row if cell is not None]
    return layout, coordinates, display_order


def _region_filter(ledger: MatrixLedger, tx_ids: Iterable[str], region: str | None) -> list[str]:
    if region is None:
        return list(tx_ids)
    return [tx_id for tx_id in tx_ids if ledger.transactions[tx_id].region == region]


def physical_sequence(ledger: MatrixLedger, name: str, region: str | None = None) -> list[str]:
    if name not in PHYSICAL_TRAVERSALS:
        raise TraversalError(f"Not a physical traversal: {name}")
    rows = len(ledger.layout)
    cols = len(ledger.layout[0]) if rows else 0
    visited: list[str] = []

    def add(r: int, c: int) -> None:
        tx_id = ledger.layout[r][c]
        if tx_id is not None:
            visited.append(tx_id)

    if name == "left_to_right":
        for r in range(rows):
            for c in range(cols):
                add(r, c)
    elif name == "right_to_left":
        for r in range(rows):
            for c in range(cols - 1, -1, -1):
                add(r, c)
    elif name == "top_to_bottom":
        for c in range(cols):
            for r in range(rows):
                add(r, c)
    elif name == "bottom_to_top":
        for c in range(cols):
            for r in range(rows - 1, -1, -1):
                add(r, c)
    elif name == "snake_horizontal":
        for r in range(rows):
            columns = range(cols) if r % 2 == 0 else range(cols - 1, -1, -1)
            for c in columns:
                add(r, c)
    elif name == "snake_vertical":
        for c in range(cols):
            row_iter = range(rows) if c % 2 == 0 else range(rows - 1, -1, -1)
            for r in row_iter:
                add(r, c)
    return _region_filter(ledger, visited, region)


def spatial_neighbour(ledger: MatrixLedger, tx_id: str, relation: str) -> str | None:
    if tx_id not in ledger.coordinates:
        raise LayoutError(f"Transaction has no coordinate: {tx_id}")
    coord = ledger.coordinates[tx_id]
    offsets = {
        "left": (0, -1),
        "right": (0, 1),
        "up": (-1, 0),
        "down": (1, 0),
    }
    try:
        dr, dc = offsets[relation]
    except KeyError as exc:
        raise TraversalError(f"Unknown spatial relation: {relation}") from exc
    r, c = coord.row + dr, coord.column + dc
    if r < 0 or c < 0 or r >= len(ledger.layout) or c >= len(ledger.layout[0]):
        return None
    return ledger.layout[r][c]


def traversal_neighbour(sequence: list[str], tx_id: str, relation: str) -> str | None:
    if relation not in {"previous", "next"}:
        raise TraversalError(f"Unknown traversal relation: {relation}")
    try:
        index = sequence.index(tx_id)
    except ValueError as exc:
        raise TraversalError(f"Transaction {tx_id} is absent from active traversal") from exc
    target = index - 1 if relation == "previous" else index + 1
    if target < 0 or target >= len(sequence):
        return None
    return sequence[target]


def path_metrics(ledger: MatrixLedger, visited: list[str]) -> dict[str, int | float]:
    if not visited:
        return {"visit_count": 0, "manhattan_distance": 0, "turn_count": 0, "region_crossings": 0}
    distance = 0
    turns = 0
    crossings = 0
    previous_vector: tuple[int, int] | None = None
    for left, right in zip(visited, visited[1:]):
        a = ledger.coordinates[left]
        b = ledger.coordinates[right]
        vector = (b.row - a.row, b.column - a.column)
        distance += abs(vector[0]) + abs(vector[1])
        normalized = (
            0 if vector[0] == 0 else (1 if vector[0] > 0 else -1),
            0 if vector[1] == 0 else (1 if vector[1] > 0 else -1),
        )
        if previous_vector is not None and normalized != previous_vector:
            turns += 1
        previous_vector = normalized
        if ledger.transactions[left].region != ledger.transactions[right].region:
            crossings += 1
    return {
        "visit_count": len(visited),
        "manhattan_distance": distance,
        "turn_count": turns,
        "region_crossings": crossings,
    }
