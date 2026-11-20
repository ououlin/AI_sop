"""
角色权限定义与检查
RBAC: 操作员 / 线长 / 管理员
"""

from enum import Enum
from typing import List, Set


class Role(str, Enum):
    """用户角色"""
    OPERATOR = "operator"      # 操作员：执行SOP、查看本工位
    SUPERVISOR = "supervisor"  # 线长：查看产线看板、处理告警、导出报告
    ADMIN = "admin"            # 管理员：管理SOP、配置工位、管理用户


# 角色权限矩阵
ROLE_PERMISSIONS: dict = {
    Role.OPERATOR: {
        "sop:execute", "sop:view", "camera:view", "video:view",
        "record:view:own",
    },
    Role.SUPERVISOR: {
        "sop:execute", "sop:view", "camera:view", "video:view",
        "sop:skip",
        "record:view:all", "record:export", "alarm:acknowledge",
        "station:view", "line:view",
    },
    Role.ADMIN: {
        "sop:execute", "sop:view", "sop:edit", "sop:delete",
        "sop:skip",
        "camera:view", "camera:manage", "video:view",
        "record:view:all", "record:export", "record:delete",
        "alarm:acknowledge", "alarm:manage",
        "station:view", "station:manage", "line:view",
        "user:manage",
    },
}


def has_permission(role: str, permission: str) -> bool:
    """检查角色是否拥有指定权限"""
    try:
        r = Role(role)
    except ValueError:
        return False
    perms = ROLE_PERMISSIONS.get(r, set())
    return permission in perms


def get_role_permissions(role: str) -> Set[str]:
    """获取角色的所有权限"""
    try:
        r = Role(role)
    except ValueError:
        return set()
    return ROLE_PERMISSIONS.get(r, set())


# 公开端点（不需要认证）
PUBLIC_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/station/report",
    "/api/v1/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}
