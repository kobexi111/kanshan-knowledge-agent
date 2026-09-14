"""FastAPI application entry point for the MVP backend."""

import json
import os
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.ai_client import AiApiError, AiClient
from app.models import (
    GenerateRouteRequest,
    GenerateRouteResponse,
    HealthResponse,
    ZhihuQuestionAnswersRequest,
    ZhihuQuestionAnswersResponse,
    ZhihuSearchRequest,
    ZhihuSearchResponse,
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
