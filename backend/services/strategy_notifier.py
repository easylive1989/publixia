"""Strategy notifier — P3 stub.

The engine calls these on every state transition that should produce a
user-visible notification. P3 ships log-only bodies so the state machine
has a stable interface. P4 will swap them to:
  - notify_signal: post a Discord embed to users.discord_webhook_url
    (with system fallback if the user hasn't configured one).
  - notify_runtime_error: dual-channel post (user + ops global webhook).
"""
import logging

logger = logging.getLogger(__name__)


def notify_signal(strategy: dict, kind: str, today_bar: dict) -> None:
    """Called on ENTRY_SIGNAL or EXIT_SIGNAL writes. P3: log only."""
    logger.info(
        "strategy_notify_signal "
        "strategy_id=%s user_id=%s kind=%s contract=%s direction=%s "
        "signal_date=%s close=%s",
        strategy.get("id"),
        strategy.get("user_id"),
        kind,
        strategy.get("contract"),
        strategy.get("direction"),
        today_bar.get("date"),
        today_bar.get("close"),
    )


def notify_runtime_error(strategy: dict, error: Exception) -> None:
    """Called when evaluate_one() raises. P3: log only.
    Message is truncated to 500 chars to keep the log line legible."""
    logger.warning(
        "strategy_notify_runtime_error "
        "strategy_id=%s user_id=%s error=%s",
        strategy.get("id"),
        strategy.get("user_id"),
        str(error)[:500],
    )
