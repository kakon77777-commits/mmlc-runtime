from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable

import sympy as sp

from .errors import DomainError, TypeCheckError, UnknownOperatorError
from .values import is_numeric, is_symbolic

Evaluator = Callable[[Any, Any, dict[str, Any]], Any]
Auditor = Callable[[Any, Any, Any, dict[str, Any]], Any]
DomainCheck = Callable[[Any, Any, dict[str, Any]], None]
TypeCheck = Callable[[Any, Any, dict[str, Any]], None]


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    version: str
    arity: int
    evaluator: Evaluator
    auditor: Auditor
    domain_check: DomainCheck
    type_check: TypeCheck

    @property
    def lock_name(self) -> str:
        return f"{self.name}@{self.version}"


class OperatorRegistry:
    def __init__(self) -> None:
        self._operators: dict[str, OperatorSpec] = {}

    def register(self, spec: OperatorSpec) -> None:
        self._operators[spec.name] = spec

    def get(self, name: str) -> OperatorSpec:
        try:
            return self._operators[name]
        except KeyError as exc:
            raise UnknownOperatorError(f"Unknown operator: {name}") from exc

    def lock(self) -> dict[str, str]:
        return {name: spec.version for name, spec in sorted(self._operators.items())}

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._operators))


def _numeric_or_symbolic(value: Any) -> bool:
    return is_numeric(value) or is_symbolic(value)


def _binary_type(base: Any, operand: Any, context: dict[str, Any]) -> None:
    if not _numeric_or_symbolic(base) or not _numeric_or_symbolic(operand):
        raise TypeCheckError(
            f"Expected numeric or symbolic operands, got {type(base).__name__}, {type(operand).__name__}"
        )


def _unary_type(base: Any, operand: Any, context: dict[str, Any]) -> None:
    if not _numeric_or_symbolic(base):
        raise TypeCheckError(f"Expected numeric or symbolic base, got {type(base).__name__}")


def _noop_domain(base: Any, operand: Any, context: dict[str, Any]) -> None:
    return None



def _divide_eval(base: Any, operand: Any, context: dict[str, Any]) -> Any:
    if isinstance(base, (int, Fraction)) and isinstance(operand, (int, Fraction)):
        return Fraction(base, operand)
    return base / operand


def _division_domain(base: Any, operand: Any, context: dict[str, Any]) -> None:
    if is_symbolic(operand):
        if sp.simplify(operand) == 0:
            raise DomainError("Division by zero")
        return
    if operand == 0:
        raise DomainError("Division by zero")


def _substitute_type(base: Any, operand: Any, context: dict[str, Any]) -> None:
    if not is_symbolic(base):
        raise TypeCheckError("substitute requires a symbolic base")
    if not isinstance(operand, dict):
        raise TypeCheckError("substitute operand must be a mapping")


def _substitute_eval(base: Any, operand: Any, context: dict[str, Any]) -> Any:
    mapping = {sp.Symbol(str(k)): v for k, v in operand.items()}
    return sp.simplify(base.subs(mapping))


def _substitute_audit(base: Any, operand: Any, result: Any, context: dict[str, Any]) -> Any:
    return sp.simplify(result - _substitute_eval(base, operand, context))



def _affine_type(base: Any, operand: Any, context: dict[str, Any]) -> None:
    _binary_type(base, operand, context)
    scale = context.get("scale", 1)
    if not _numeric_or_symbolic(scale):
        raise TypeCheckError("affine context.scale must be numeric or symbolic")


def _affine_eval(base: Any, operand: Any, context: dict[str, Any]) -> Any:
    return context.get("scale", 1) * base + operand


def _affine_audit(base: Any, operand: Any, result: Any, context: dict[str, Any]) -> Any:
    return result - _affine_eval(base, operand, context)

def build_default_registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    specs = [
        OperatorSpec("add", "1.0.0", 2, lambda b, a, c: b + a, lambda b, a, r, c: r - b - a, _noop_domain, _binary_type),
        OperatorSpec("subtract", "1.0.0", 2, lambda b, a, c: b - a, lambda b, a, r, c: r - b + a, _noop_domain, _binary_type),
        OperatorSpec("multiply", "1.0.0", 2, lambda b, a, c: b * a, lambda b, a, r, c: r - b * a, _noop_domain, _binary_type),
        OperatorSpec("divide", "1.0.0", 2, _divide_eval, lambda b, a, r, c: a * r - b, _division_domain, _binary_type),
        OperatorSpec("power", "1.0.0", 2, lambda b, a, c: b ** a, lambda b, a, r, c: r - b ** a, _noop_domain, _binary_type),
        OperatorSpec("negate", "1.0.0", 1, lambda b, a, c: -b, lambda b, a, r, c: r + b, _noop_domain, _unary_type),
        OperatorSpec("identity", "1.0.0", 1, lambda b, a, c: b, lambda b, a, r, c: r - b, _noop_domain, _unary_type),
        OperatorSpec("substitute", "0.1.0-preview", 2, _substitute_eval, _substitute_audit, _noop_domain, _substitute_type),
        OperatorSpec("affine", "0.1.0", 2, _affine_eval, _affine_audit, _noop_domain, _affine_type),
    ]
    for spec in specs:
        reg.register(spec)
    return reg
