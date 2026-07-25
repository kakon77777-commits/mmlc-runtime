class MMLCError(Exception):
    """Base error for explicit, structured runtime failures."""


class SchemaValidationError(MMLCError):
    pass


class DuplicateIdError(MMLCError):
    pass


class UnknownOperatorError(MMLCError):
    pass


class TypeCheckError(MMLCError):
    pass


class DomainError(MMLCError):
    pass


class DependencyError(MMLCError):
    pass


class DependencyCycleError(DependencyError):
    pass


class MissingReferenceError(DependencyError):
    pass


class LayoutError(MMLCError):
    pass


class TraversalError(MMLCError):
    pass


class TraversalSemanticError(TraversalError):
    pass


class FDCSConfigurationError(MMLCError):
    pass


class InterventionError(MMLCError):
    pass
