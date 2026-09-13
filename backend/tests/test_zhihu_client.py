"""Tests for the Zhihu adapter without sending external requests."""

import httpx
import pytest

from app.zhihu_client import ZhihuApiError, ZhihuClient


@pytest.fixture
def anyio_backend() -> str:
    """Keep async tests on asyncio, the runtime used by this application."""

    return "asyncio"


@pytest.mark.anyio
async def test_search_builds_documented_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(
            "https://developer.zhihu.com/api/v1/content/zhihu_search?"
        )
        assert request.url.params["Query"] == "AI Agent"
        assert request.url.params["Count"] == "5"
        assert request.url.params["SortBy"] == "VoteUpCount:desc"
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert request.headers["X-Request-Timestamp"].isdigit()
        return httpx.Response(
            200,
            json={"Code": 0, "Message": "success", "Data": {"Items": []}},
        )

    client = ZhihuClient(
        "test-secret",
        transport=httpx.MockTransport(handler),
    )

    data = await client.search(" AI Agent ", 5, "VoteUpCount:desc")

    assert data == {"Items": []}


@pytest.mark.anyio
async def test_search_normalizes_api_error() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"Code": 40101, "Message": "invalid credential"},
        )

    client = ZhihuClient(
        "bad-secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ZhihuApiError, match="invalid credential"):
        await client.search("AI")


@pytest.mark.anyio
async def test_question_answers_builds_documented_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/content/question_answers")
        assert request.url.params["QuestionUrl"] == (
            "https://www.zhihu.com/question/123456"
        )
        assert request.url.params["Offset"] == "0"
        assert request.url.params["Limit"] == "20"
        return httpx.Response(
            200,
            json={"Code": 0, "Message": "success", "Data": {"Items": []}},
        )

    client = ZhihuClient(
        "test-secret",
        transport=httpx.MockTransport(handler),
    )

    data = await client.question_answers(
        "https://www.zhihu.com/question/123456"
    )

    assert data == {"Items": []}


def test_search_requires_secret() -> None:
    client = ZhihuClient(access_secret="")
    client.access_secret = None

    with pytest.raises(ZhihuApiError, match="ZHIHU_ACCESS_SECRET"):
        client._headers()
