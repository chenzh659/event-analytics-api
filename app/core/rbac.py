"""Role-based access control definitions."""

from enum import StrEnum


class RoleName(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    CLIENT_APP = "client_app"


class Permission(StrEnum):
    EVENTS_WRITE = "events:write"
    EVENTS_BATCH = "events:batch"
    EVENTS_READ = "events:read"
    METRICS_READ = "metrics:read"
    USERS_MANAGE = "users:manage"
    JOBS_TRIGGER = "jobs:trigger"
    QUEUE_READ = "queue:read"
    HEALTH_READ = "health:read"


ROLE_PERMISSIONS: dict[RoleName, set[Permission]] = {
    RoleName.CLIENT_APP: {
        Permission.EVENTS_WRITE,
        Permission.EVENTS_BATCH,
        Permission.HEALTH_READ,
    },
    RoleName.ANALYST: {
        Permission.EVENTS_WRITE,
        Permission.EVENTS_BATCH,
        Permission.EVENTS_READ,
        Permission.METRICS_READ,
        Permission.HEALTH_READ,
    },
    RoleName.ADMIN: {
        Permission.EVENTS_WRITE,
        Permission.EVENTS_BATCH,
        Permission.EVENTS_READ,
        Permission.METRICS_READ,
        Permission.USERS_MANAGE,
        Permission.JOBS_TRIGGER,
        Permission.QUEUE_READ,
        Permission.HEALTH_READ,
    },
}


def has_permission(role: str, permission: Permission) -> bool:
    try:
        role_name = RoleName(role)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(role_name, set())
