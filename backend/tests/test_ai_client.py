"""Tests for OpenAI-compatible structured response handling."""

import asyncio
import json

import httpx
import pytest

from app.ai_client import AiApiError, AiClient
from app.models import KnowledgeAnalysis


def analysis_payload() -> dict:
    topic = {
        "name": "线性代数",
        "description": "向量与矩阵基础",
        "reason": "理解当前主题所需",
        "search_query": "线性代数 入门",
    }
    return {
        "title": "机器学习基础",
        "summary": "介绍机器学习的基本概念",
        "current_level": "基础",
        "core_concepts": ["监督学习"],
        "prerequisites": [topic],
        "advanced_topics": [{**topic, "name": "深度学习"}],
    }


def test_accepts_markdown_fenced_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        assert "JSON Schema" in request_body["messages"][0]["content"]
        content = "```json\n" + json.dumps(analysis_payload(), ensure_ascii=False) + "\n```"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    client = AiClient(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(client.analyze_content("测试内容"))

    assert isinstance(result, KnowledgeAnalysis)
    assert result.title == "机器学习基础"


def test_reports_invalid_schema_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = analysis_payload()
        payload["current_level"] = "专家"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        )

    client = AiClient(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AiApiError, match="current_level"):
        asyncio.run(client.analyze_content("测试内容"))
