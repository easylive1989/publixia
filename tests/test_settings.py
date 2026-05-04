"""BE-A: settings.py tests."""
import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))


def test_settings_db_path_env_override(monkeypatch):
    """DB_PATH env var overrides the default."""
    monkeypatch.setenv("DB_PATH", ":memory:")
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    assert settings_mod.settings.db_path == ":memory:"


def test_settings_secret_finmind_token_not_in_repr(monkeypatch):
    """SecretStr must not leak the token in repr/str."""
    monkeypatch.setenv("FINMIND_TOKEN", "super-secret")
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    s = settings_mod.settings
    assert "super-secret" not in repr(s)
    assert "super-secret" not in str(s)
    assert s.finmind_token.get_secret_value() == "super-secret"


def test_settings_cors_origins_default():
    """Default CORS allows the production frontend."""
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    assert "https://paul-learning.dev" in settings_mod.settings.cors_origins


def test_settings_log_level_default():
    """Default log level is INFO."""
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    assert settings_mod.settings.log_level == "INFO"
