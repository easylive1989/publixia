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


class MarketClosed(FetcherError):
    """資料源回應正常，但今天沒有盤（休市／未開盤）—— 不是故障。

    跟其他 ``FetcherError`` 分開，是為了讓呼叫端能決定要吵到什麼程度：
    休市是可預期的非事件，MIS 壞掉則必須有人知道。兩者都回 None 的話，
    這個區別就消失了。
    """


class RepositoryError(StockDashboardError):
    """SQL operation failed for an unrecoverable reason."""


class AlertEvaluationError(StockDashboardError):
    """Alert evaluator produced an unexpected result."""
