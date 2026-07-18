from app.core.rbac import Permission, RoleName, has_permission
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("Secret123!")
    assert hashed != "Secret123!"
    assert verify_password("Secret123!", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip():
    token = create_access_token(subject="user-1", role="admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "admin"


def test_rbac_matrix():
    assert has_permission(RoleName.CLIENT_APP, Permission.EVENTS_WRITE)
    assert not has_permission(RoleName.CLIENT_APP, Permission.METRICS_READ)
    assert has_permission(RoleName.ANALYST, Permission.METRICS_READ)
    assert has_permission(RoleName.ADMIN, Permission.USERS_MANAGE)
    assert not has_permission("unknown", Permission.HEALTH_READ)
