"""Minimal Zhihu OAuth flow using only endpoints documented by Zhihu."""

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

AUTHORIZE_URL = "https://openapi.zhihu.com/authorize"
ACCESS_TOKEN_URL = "https://openapi.zhihu.com/access_token"
FLOW_COOKIE = "kanshan_oauth_flow"
SESSION_COOKIE = "kanshan_session"


class OAuthError(RuntimeError):
    """Safe OAuth configuration, transport, or response error."""


@dataclass(frozen=True)
class OAuthConfig:
    app_id: str
    app_key: str
    redirect_uri: str
    frontend_url: str
    session_secret: str

    @classmethod
    def from_env(cls) -> "OAuthConfig":
        values = {
            "app_id": os.getenv("ZHIHU_OAUTH_APP_ID", "").strip(),
            "app_key": os.getenv("ZHIHU_OAUTH_APP_KEY", "").strip(),
            "redirect_uri": os.getenv("ZHIHU_OAUTH_REDIRECT_URI", "").strip(),
            "frontend_url": os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/"),
            "session_secret": os.getenv("SESSION_SECRET", "").strip(),
        }
        missing = [
            env_name
            for key, env_name in (
                ("app_id", "ZHIHU_OAUTH_APP_ID"),
                ("app_key", "ZHIHU_OAUTH_APP_KEY"),
                ("redirect_uri", "ZHIHU_OAUTH_REDIRECT_URI"),
                ("session_secret", "SESSION_SECRET"),
            )
            if not values[key]
        ]
        if missing:
            raise OAuthError(f"知乎 OAuth 尚未配置：{', '.join(missing)}")
        return cls(**values)

    @property
    def secure_cookie(self) -> bool:
        return self.redirect_uri.startswith("https://")


def authorization_url(config: OAuthConfig) -> str:
    """Build the exact documented authorization request parameters."""

    query = urlencode({
        'redirect_uri': config.redirect_uri,
        'app_id': config.app_id,
        'response_type': 'code',
    })
    return f"{AUTHORIZE_URL}?{query}"


def new_flow_cookie(config: OAuthConfig) -> str:
    return _encrypt(
        {"nonce": secrets.token_urlsafe(24), "expires_at": int(time.time()) + 600},
        config.session_secret,
    )


def validate_flow_cookie(value: str | None, config: OAuthConfig) -> None:
    data = _decrypt(value, config.session_secret)
    if not data or not data.get("nonce") or int(data.get("expires_at", 0)) < time.time():
        raise OAuthError("OAuth 授权流程已失效，请重新点击知乎登录。")


async def exchange_access_token(
    authorization_code: str,
    config: OAuthConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Exchange the documented authorization_code for an access token."""

    try:
        async with httpx.AsyncClient(timeout=30, transport=transport) as client:
            response = await client.post(
                ACCESS_TOKEN_URL,
                data={
                    "app_id": config.app_id,
                    "app_key": config.app_key,
                    "grant_type": "authorization_code",
                    "redirect_uri": config.redirect_uri,
                    "code": authorization_code,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise OAuthError("知乎 OAuth 换取 access_token 失败。") from error

    try:
        data = response.json()
        access_token = data["access_token"]
        token_type = data["token_type"]
        expires_in = int(data["expires_in"])
    except (ValueError, KeyError, TypeError) as error:
        raise OAuthError("知乎 OAuth 返回了无法识别的 Token 数据。") from error
    if not isinstance(access_token, str) or not access_token or expires_in <= 0:
        raise OAuthError("知乎 OAuth 返回的 Token 数据不完整。")
    return {
        "access_token": access_token,
        "token_type": str(token_type),
        "expires_at": int(time.time()) + expires_in,
    }


def session_cookie(token_data: dict[str, Any], config: OAuthConfig) -> str:
    return _encrypt(token_data, config.session_secret)


def read_session(value: str | None, config: OAuthConfig) -> bool:
    data = _decrypt(value, config.session_secret)
    return bool(
        data
        and data.get("access_token")
        and int(data.get("expires_at", 0)) > time.time()
    )


def _fernet(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def _encrypt(data: dict[str, Any], secret: str) -> str:
    payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return _fernet(secret).encrypt(payload).decode("ascii")


def _decrypt(value: str | None, secret: str) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        data = json.loads(_fernet(secret).decrypt(value.encode("ascii")).decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
