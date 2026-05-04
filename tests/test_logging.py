"""BE-A: logging setup tests."""
import importlib
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))


def test_setup_logging_sets_root_to_info():
    from core.logging import setup_logging
    setup_logging()
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_suppresses_third_party():
    from core.logging import setup_logging
    setup_logging()
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("apscheduler").level == logging.WARNING


def test_setup_logging_respects_log_level_env(monkeypatch):
    """LOG_LEVEL=DEBUG raises the root logger to DEBUG."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    import core.logging as logging_mod
    importlib.reload(logging_mod)
    logging_mod.setup_logging()
    assert logging.getLogger().level == logging.DEBUG
