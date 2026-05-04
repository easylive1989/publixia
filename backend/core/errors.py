"""Exception hierarchy used across layers. See CONVENTIONS.md §4.3.

These classes are defined now but most adopters will arrive in BE-B / BE-C /
Phase 4 (AUTH-) as each layer is refactored.
"""


class StockDashboardError(Exception):
    """Base class for all in-app domain errors."""


class FetcherError(StockDashboardError):
    """Persistent failure fetching from an external data source."""


class FetcherParseError(FetcherError):
    """Response body did not match the expected shape."""


class RepositoryError(StockDashboardError):
    """SQL operation failed for an unrecoverable reason."""


class AlertEvaluationError(StockDashboardError):
    """Alert evaluator produced an unexpected result."""


class AuthError(StockDashboardError):
    """Authentication / authorisation failure (Phase 4 will adopt)."""
