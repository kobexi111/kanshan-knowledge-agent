"""Tests for the server-side Zhihu OAuth skeleton."""

import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.oauth import (
    OAuthConfig,
    OAuthError,
    authorization_url,
    exchange_access_token,
    new_flow_cookie,
    read_session,
    session_cookie,
    validate_flow_cookie,
)


@pytest.fixture
def config() -> OAuthConfig:
    return OAuthConfig(
        app_id="app-id",
        app_key="app-key",
        redirect_uri="https://api.example.com/api/auth/zhihu/callback",
        frontend_url="https://web.example.com",
        session_secret="a-long-random-session-secret-for-tests",
    )


def test_authorization_url_uses_only_documented_parameters(config: OAuthConfig) -> None:
    parsed = urlparse(authorization_url(config))
    assert parsed.scheme == "https"
    assert parsed.netloc == "openapi.zhihu.com"
    assert parse_qs(parsed.query) == {
        "redirect_uri": [config.redirect_uri],
        "app_id": [config.app_id],
        "response_type": ["code"],
    }


def test_flow_marker_and_encrypted_session(config: OAuthConfig) -> None:
    flow = new_flow_cookie(config)
    validate_flow_cookie(flow, config)
    with pytest.raises(OAuthError):
        validate_flow_cookie("invalid", config)

    value = session_cookie(
        {"access_token": "private", "token_type": "Bearer", "expires_at": 4102444800},
        config,
    )
    assert "private" not in value
    assert read_session(value, config) is True
    assert read_session("invalid", config) is False


def test_exchange_access_token_uses_documented_form(config: OAuthConfig) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://openapi.zhihu.com/access_token"
        assert parse_qs(request.content.decode()) == {
            "app_id": ["app-id"],
            "app_key": ["app-key"],
            "grant_type": ["authorization_code"],
            "redirect_uri": [config.redirect_uri],
            "code": ["authorization-code"],
        }
        return httpx.Response(
            200,
            json={"access_token": "token", "token_type": "Bearer", "expires_in": 3600},
        )

    token = asyncio.run(
        exchange_access_token(
            "authorization-code",
            config,
            transport=httpx.MockTransport(handler),
        )
    )
    assert token["access_token"] == "token"
    assert token["token_type"] == "Bearer"
