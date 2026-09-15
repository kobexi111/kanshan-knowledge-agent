"""FastAPI application entry point for the MVP backend."""

import json
import os
import time
from collections.abc import AsyncIterator

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from app.ai_client import AiApiError, AiClient
from app.models import (
    GenerateRouteRequest,
    GenerateRouteResponse,
    HealthResponse,
    AuthSessionResponse,
    ZhihuQuestionAnswersRequest,
    ZhihuQuestionAnswersResponse,
    ZhihuSearchRequest,
    ZhihuSearchResponse,
)
from app.oauth import (
    FLOW_COOKIE,
    PROFILE_COOKIE,
    SESSION_COOKIE,
    OAuthConfig,
    OAuthError,
    authorization_url,
    exchange_access_token,
    new_flow_cookie,
    new_profile_cookie,
    profile_identifier,
    read_session,
    session_profile_id,
    session_cookie,
    validate_flow_cookie,
)
from app.real_route import build_real_route, stream_real_route
from app.zhihu_client import ZhihuApiError, ZhihuClient

app = FastAPI(
    title="Zhihu Knowledge Agent API",
    version="0.1.0",
    description="Real Zhihu retrieval workflow for the Zhihu Knowledge Agent MVP.",
)

# The local Next.js development server needs browser access to this API.
local_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
deployed_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*local_origins, *deployed_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report whether the backend process is ready to receive requests."""

    return HealthResponse()


@app.get("/api/auth/zhihu/login")
async def zhihu_login(
    profile_value: str | None = Cookie(default=None, alias=PROFILE_COOKIE),
) -> RedirectResponse:
    """Start the documented Zhihu authorization-code flow."""

    try:
        config = OAuthConfig.from_env()
    except OAuthError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    response = RedirectResponse(authorization_url(config), status_code=302)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=config.secure_cookie,
        httponly=True,
        samesite="none" if config.secure_cookie else "lax",
    )
    response.set_cookie(
        FLOW_COOKIE,
        new_flow_cookie(config),
        max_age=600,
        httponly=True,
        secure=config.secure_cookie,
        samesite="lax",
        path="/",
    )
    if not profile_identifier(profile_value, config):
        response.set_cookie(
            PROFILE_COOKIE,
            new_profile_cookie(),
            max_age=31_536_000,
            httponly=True,
            secure=config.secure_cookie,
            samesite="lax",
            path="/",
        )
    return response


@app.get("/api/auth/zhihu/switch")
async def zhihu_switch_account() -> RedirectResponse:
    """Clear the app session and start a fresh Zhihu authorization flow."""

    try:
        config = OAuthConfig.from_env()
    except OAuthError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    response = RedirectResponse(authorization_url(config), status_code=302)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=config.secure_cookie,
        httponly=True,
        samesite="none" if config.secure_cookie else "lax",
    )
    response.set_cookie(
        FLOW_COOKIE,
        new_flow_cookie(config),
        max_age=600,
        httponly=True,
        secure=config.secure_cookie,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        PROFILE_COOKIE,
        new_profile_cookie(),
        max_age=31_536_000,
        httponly=True,
        secure=config.secure_cookie,
        samesite="lax",
        path="/",
    )
    return response


@app.get("/api/auth/zhihu/callback")
async def zhihu_callback(
    authorization_code: str = Query(min_length=1),
    flow_cookie: str | None = Cookie(default=None, alias=FLOW_COOKIE),
) -> RedirectResponse:
    """Exchange the code server-side and create an encrypted browser session."""

    try:
        config = OAuthConfig.from_env()
    except OAuthError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    try:
        validate_flow_cookie(flow_cookie, config)
        token_data = await exchange_access_token(authorization_code, config)
    except OAuthError:
        return RedirectResponse(
            f"{config.frontend_url}/login?oauth=error",
            status_code=302,
        )

    response = RedirectResponse(f"{config.frontend_url}/?oauth=success", status_code=302)
    response.delete_cookie(FLOW_COOKIE, path="/")
    response.set_cookie(
        SESSION_COOKIE,
        session_cookie(token_data, config),
        max_age=max(1, int(token_data["expires_at"] - time.time())),
        httponly=True,
        secure=config.secure_cookie,
        samesite="none" if config.secure_cookie else "lax",
        path="/",
    )
    return response


@app.get("/api/auth/session", response_model=AuthSessionResponse)
async def auth_session(
    session_value: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    profile_value: str | None = Cookie(default=None, alias=PROFILE_COOKIE),
) -> AuthSessionResponse:
    """Return only public authorization state, never the OAuth access token."""

    try:
        config = OAuthConfig.from_env()
        authenticated = read_session(session_value, config)
        profile_id = profile_identifier(profile_value, config)
        if not profile_id:
            profile_id = session_profile_id(session_value, config)
        configured = True
    except OAuthError:
        authenticated = False
        profile_id = None
        configured = False
    return AuthSessionResponse(
        authenticated=authenticated,
        configured=configured,
        provider="zhihu" if authenticated else None,
        profile_id=profile_id,
    )


@app.post("/api/auth/logout", response_model=AuthSessionResponse)
async def auth_logout() -> JSONResponse:
    """Remove the encrypted OAuth session cookie."""

    try:
        config = OAuthConfig.from_env()
    except OAuthError:
        config = None
    response = JSONResponse(AuthSessionResponse(authenticated=False).model_dump())
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=config.secure_cookie if config else False,
        httponly=True,
        samesite="none" if config and config.secure_cookie else "lax",
    )
    return response


@app.get("/api/auth/logout")
async def auth_logout_redirect() -> RedirectResponse:
    """Reliably clear the browser session and return to the login screen."""

    try:
        config = OAuthConfig.from_env()
    except OAuthError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    response = RedirectResponse(
        f"{config.frontend_url}/login?logout=success",
        status_code=302,
    )
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=config.secure_cookie,
        httponly=True,
        samesite="none" if config.secure_cookie else "lax",
    )
    return response


def get_zhihu_client() -> ZhihuClient:
    """Create the API client from server-side environment configuration."""

    return ZhihuClient()


def get_ai_client() -> AiClient:
    """Create the AI client from server-side environment configuration."""

    return AiClient()


@app.post(
    "/api/routes/generate",
    response_model=GenerateRouteResponse,
)
async def generate_route(
    request: GenerateRouteRequest,
    zhihu_client: ZhihuClient = Depends(get_zhihu_client),
    ai_client: AiClient = Depends(get_ai_client),
) -> GenerateRouteResponse:
    """Build an AI-planned route whose materials come from the Zhihu API."""

    try:
        return await build_real_route(request, zhihu_client, ai_client)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ZhihuApiError as error:
        rate_limited = error.status == 429 or "rate limit" in str(error).lower()
        status_code = 429 if rate_limited else (
            503 if "ZHIHU_ACCESS_SECRET" in str(error) else 502
        )
        detail = (
            "知乎 API 调用频率受限，请稍后再试。"
            if rate_limited
            else f"知乎 API：{error}"
        )
        raise HTTPException(status_code=status_code, detail=detail) from error
    except AiApiError as error:
        status_code = 429 if error.status == 429 else (
            503 if "缺少 AI 配置" in str(error) else 502
        )
        raise HTTPException(status_code=status_code, detail=str(error)) from error


@app.post("/api/routes/generate/stream")
async def generate_route_stream(
    request: GenerateRouteRequest,
    zhihu_client: ZhihuClient = Depends(get_zhihu_client),
    ai_client: AiClient = Depends(get_ai_client),
) -> StreamingResponse:
    """Stream newline-delimited JSON whenever one route stage is complete."""

    async def events() -> AsyncIterator[str]:
        try:
            async for event in stream_real_route(request, zhihu_client, ai_client):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except ValueError as error:
            message = str(error)
        except ZhihuApiError as error:
            rate_limited = error.status == 429 or "rate limit" in str(error).lower()
            message = (
                "知乎 API 调用频率受限，请稍后再试。"
                if rate_limited
                else f"知乎 API：{error}"
            )
        except AiApiError as error:
            message = str(error)
        else:
            return
        yield json.dumps({"type": "error", "message": message}, ensure_ascii=False) + "\n"

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/zhihu/search", response_model=ZhihuSearchResponse)
async def search_zhihu(
    request: ZhihuSearchRequest,
    client: ZhihuClient = Depends(get_zhihu_client),
) -> ZhihuSearchResponse:
    """Experimentally call the supplied Zhihu Open Platform search endpoint."""

    try:
        data = await client.search(request.query, request.count, request.sort_by)
    except ZhihuApiError as error:
        status_code = 503 if "ZHIHU_ACCESS_SECRET" in str(error) else 502
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return ZhihuSearchResponse(query=request.query.strip(), data=data)


@app.post(
    "/api/zhihu/question-answers",
    response_model=ZhihuQuestionAnswersResponse,
)
async def get_zhihu_question_answers(
    request: ZhihuQuestionAnswersRequest,
    client: ZhihuClient = Depends(get_zhihu_client),
) -> ZhihuQuestionAnswersResponse:
    """Fetch real answer summaries for one Zhihu question."""

    try:
        data = await client.question_answers(
            str(request.question_url),
            request.offset,
            request.count,
        )
    except ZhihuApiError as error:
        status_code = 503 if "ZHIHU_ACCESS_SECRET" in str(error) else 502
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return ZhihuQuestionAnswersResponse(
        question_url=request.question_url,
        data=data,
    )
