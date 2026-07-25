from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

import sympy as sp

from .types import MatrixRef, TemporalRef, ValueRef


def parse_value(value: Any) -> Any:
    if isinstance(value, dict) and "ref" in value:
        return ValueRef(str(value["ref"]), str(value.get("field", "result")))
    if isinstance(value, dict) and "temporal_ref" in value:
        return TemporalRef(
            series_id=str(value["temporal_ref"]),
            lag=int(value.get("lag", 1)),
            field=str(value.get("field", "result")),
            default=parse_value(value.get("default")),
            has_default="default" in value,
        )
    if isinstance(value, dict) and "matrix_ref" in value:
        relation = str(value["matrix_ref"])
        return MatrixRef(
            relation=relation,
            field=str(value.get("field", "result")),
            default=parse_value(value.get("default")),
            has_default="default" in value,
        )
    if isinstance(value, dict):
        return {str(k): parse_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [parse_value(v) for v in value]
    if isinstance(value, str):
        if value.startswith("expr:"):
            return sp.sympify(value[5:].strip())
        if value.startswith("frac:"):
            numerator, denominator = value[5:].strip().split("/", 1)
            return Fraction(int(numerator), int(denominator))
    return value


def is_symbolic(value: Any) -> bool:
    return isinstance(value, sp.Basic)


def is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float, Fraction, sp.Integer, sp.Rational, sp.Float)) and not isinstance(value, bool)


def exact_equal(left: Any, right: Any) -> bool:
    if is_symbolic(left) or is_symbolic(right):
        try:
            return sp.simplify(sp.sympify(left) - sp.sympify(right)) == 0
        except Exception:
            return left == right
    return left == right


def equivalent_value(left: Any, right: Any, tolerance: float = 1.0e-12) -> tuple[bool, str]:
    """Compare exact symbolic/rational values first, then use scaled numeric tolerance."""
    try:
        if exact_equal(left, right):
            return True, "exact"
    except Exception:
        pass
    try:
        lval = float(sp.N(left)) if is_symbolic(left) else float(left)
        rval = float(sp.N(right)) if is_symbolic(right) else float(right)
        if not (math.isfinite(lval) and math.isfinite(rval)):
            return False, "non-finite"
        scale = 1.0 + abs(lval) + abs(rval)
        delta = abs(lval - rval) / scale
        return delta <= tolerance, f"scaled_delta={delta:.3e}"
    except Exception as exc:
        return False, f"incomparable: {exc}"


def substitute_value(value: Any, bindings: dict[str, Any]) -> Any:
    """Recursively substitute symbols while preserving ledger references."""
    if isinstance(value, (ValueRef, MatrixRef, TemporalRef)):
        return value
    if isinstance(value, sp.Basic):
        mapping = {sp.Symbol(str(k)): parse_value(v) for k, v in bindings.items()}
        return sp.simplify(value.subs(mapping))
    if isinstance(value, dict):
        return {str(k): substitute_value(v, bindings) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_value(v, bindings) for v in value]
    if isinstance(value, tuple):
        return tuple(substitute_value(v, bindings) for v in value)
    return value


def free_symbols(value: Any) -> set[str]:
    symbols: set[str] = set()
    if isinstance(value, sp.Basic):
        symbols.update(str(symbol) for symbol in value.free_symbols)
    elif isinstance(value, dict):
        for child in value.values():
            symbols.update(free_symbols(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            symbols.update(free_symbols(child))
    return symbols


def numeric_abs(value: Any) -> float:
    if is_symbolic(value):
        if value.free_symbols:
            raise TypeError("symbolic residual has free symbols")
        return abs(float(value.evalf()))
    return abs(float(value))


def finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def serialize_value(value: Any) -> Any:
    if isinstance(value, ValueRef):
        return {"ref": value.tx_id, "field": value.field}
    if isinstance(value, MatrixRef):
        data = {"matrix_ref": value.relation, "field": value.field}
        if value.has_default:
            data["default"] = serialize_value(value.default)
        return data
    if isinstance(value, TemporalRef):
        data = {"temporal_ref": value.series_id, "lag": value.lag, "field": value.field}
        if value.has_default:
            data["default"] = serialize_value(value.default)
        return data
    if isinstance(value, Fraction):
        return {"type": "fraction", "numerator": value.numerator, "denominator": value.denominator}
    if isinstance(value, sp.Basic):
        return {"type": "sympy", "srepr": sp.srepr(value), "str": str(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return value
    return value
