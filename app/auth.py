"""服务端令牌绑定身份；问答正文和模型不能指定自己的权限。"""

import json
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.config import Settings


@dataclass(frozen=True)
class Principal:
    """可信身份；dataclass 自动初始化，不从问答正文构造。"""

    user_id: str
    tenant_id: str
    departments: tuple[str, ...] = ()
    admin: bool = False


DEMO_ADMIN = Principal("demo-admin", "demo", ("engineering", "ops"), True)
DEMO_READER = Principal("demo-reader", "demo")


def token_map(settings: Settings) -> dict[str, Principal]:
    """json.loads 解析服务端令牌配置；Principal 固定对应权限。"""
    raw = settings.tokens_json.get_secret_value()
    if raw:
        mapping = json.loads(raw)
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("RAG_TOKENS_JSON 必须是非空对象")
        result = {}
        for token, identity in mapping.items():
            if len(token) < 24:
                raise ValueError("非演示令牌至少需要 24 个字符")
            result[token] = Principal(**identity)
        return result
    if settings.allow_demo_auth and settings.host in {"127.0.0.1", "localhost"}:
        return {
            "demo-reader-token": DEMO_READER,
            "demo-ops-token": Principal("demo-ops", "demo", ("ops",)),
            "demo-admin-token": DEMO_ADMIN,
        }
    raise ValueError("非本机演示必须配置 RAG_TOKENS_JSON 并关闭演示认证")


def authenticate(request: Request) -> Principal:
    """从 Authorization 查身份；compare_digest 比较令牌；失败返回 401。"""
    header = request.headers.get("authorization", "")
    token = header[7:] if header.startswith("Bearer ") else ""
    for expected, principal in request.app.state.tokens.items():
        if secrets.compare_digest(token.encode(), expected.encode()):
            return principal
    raise HTTPException(401, "请提供有效访问令牌")


def require_admin(principal: Principal) -> None:
    """检查已认证身份的写权限；无权限抛出 HTTPException(403)。"""
    if not principal.admin:
        raise HTTPException(403, "当前身份不能修改知识库")
