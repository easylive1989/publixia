"""Tests for the P3 stub notifier — verifies the log call shape."""
import logging

from services.strategy_notifier import notify_signal, notify_runtime_error


def test_notify_signal_logs_strategy_kind_and_bar(caplog):
    strategy = {
        "id": 42, "user_id": 1,
        "contract": "TX", "direction": "long",
    }
    today_bar = {"date": "2026-05-15", "close": 17250.5}

    with caplog.at_level(logging.INFO):
        notify_signal(strategy, "ENTRY_SIGNAL", today_bar)

    msg = "\n".join(caplog.messages)
    assert "ENTRY_SIGNAL" in msg
    assert "strategy_id=42" in msg
    assert "user_id=1" in msg
    assert "contract=TX" in msg
    assert "2026-05-15" in msg


def test_notify_runtime_error_logs_strategy_id_and_msg(caplog):
    strategy = {"id": 7, "user_id": 1}
    err = ValueError("DSL exploded")

    with caplog.at_level(logging.WARNING):
        notify_runtime_error(strategy, err)

    msg = "\n".join(caplog.messages)
    assert "strategy_id=7" in msg
    assert "DSL exploded" in msg


def test_notify_runtime_error_truncates_long_message(caplog):
    strategy = {"id": 7, "user_id": 1}
    err = ValueError("x" * 2000)
    with caplog.at_level(logging.WARNING):
        notify_runtime_error(strategy, err)
    # The log line should not contain the full 2000 'x's.
    assert "x" * 600 not in caplog.text
