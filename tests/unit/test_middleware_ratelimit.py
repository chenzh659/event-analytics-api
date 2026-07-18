"""Unit tests for portfolio-grade reliability helpers."""

from app.core.middleware import normalize_path


def test_normalize_path_collapses_uuid():
    raw = "/api/v1/events/64860119-a957-4bff-917c-2746444017ec"
    assert normalize_path(raw) == "/api/v1/events/{id}"


def test_normalize_path_collapses_numeric_id():
    assert normalize_path("/api/v1/admin/users/42") == "/api/v1/admin/users/{id}"


def test_sliding_window_lua_is_loadable():
    # Ensure module imports and exposes enforce entrypoint
    from app.core import rate_limit

    assert callable(rate_limit.enforce_rate_limit)
    assert "ZREMRANGEBYSCORE" in rate_limit._SLIDING_WINDOW_LUA
