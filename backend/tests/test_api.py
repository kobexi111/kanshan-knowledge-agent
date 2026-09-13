"""API contract tests for the real Zhihu retrieval workflow."""

from fastapi.testclient import TestClient

from app.main import app, get_ai_client, get_zhihu_client
from app.models import (
    KnowledgeAnalysis,
    KnowledgeTopic,
    MaterialChoice,
    MaterialSelection,
)

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "zhihu-knowledge-agent",
    }


def test_generate_route_returns_real_zhihu_materials() -> None:
    class FakeZhihuClient:
        async def question_answers(
            self,
            question_url: str,
            offset: int,
            count: int,
        ) -> dict[str, object]:
            assert question_url == "https://www.zhihu.com/question/123456"
            return {
                "Items": [
                    {
                        "ContentToken": "987654",
                        "Summary": "机器学习需要理解数据、模型训练和模型评估。",
                        "Url": (
                            "https://www.zhihu.com/question/123456/answer/987654"
                        ),
                    }
                ],
                "Paging": {"IsEnd": True},
            }

        async def search(
            self,
            query: str,
            count: int,
            sort_by: str | None = None,
        ) -> dict[str, object]:
            assert "机器学习" in query
            prefix = "prerequisite" if "数学" in query else "advanced"
            return {
                "Items": [
                    {
                        "ContentID": f"{prefix}-{index}",
                        "Title": f"真实知乎资料 {index}",
                        "Url": f"https://zhuanlan.zhihu.com/p/{prefix}-{index}",
                        "VoteUpCount": index,
                    }
                    for index in range(1, 7)
                ]
            }

    class FakeAiClient:
        async def analyze_content(self, content: str) -> KnowledgeAnalysis:
            assert "机器学习" in content
            return KnowledgeAnalysis(
                title="机器学习基础",
                summary="理解机器学习的基本过程。",
                current_level="基础",
                core_concepts=["数据", "训练", "评估"],
                prerequisites=[
                    KnowledgeTopic(
                        name="数学基础",
                        description="理解必要数学概念。",
                        reason="模型训练依赖数学表达。",
                        search_query="机器学习 数学基础",
                    )
                ],
                advanced_topics=[
                    KnowledgeTopic(
                        name="模型优化",
                        description="进一步优化模型表现。",
                        reason="掌握基础后继续提高。",
                        search_query="机器学习 模型优化",
                    )
                ],
            )

        async def select_materials(
            self,
            analysis: KnowledgeAnalysis,
            candidates: list[dict[str, object]],
        ) -> MaterialSelection:
            prerequisite = next(
                item for item in candidates if item["stage"] == "prerequisite"
            )
            advanced = next(
                item for item in candidates if item["stage"] == "advanced"
            )
            return MaterialSelection(
                prerequisites=[
                    MaterialChoice(
                        candidate_id=str(prerequisite["candidate_id"]),
                        topic_name="数学基础",
                        reason="内容基础且质量指标较好。",
                    )
                ],
                advanced=[
                    MaterialChoice(
                        candidate_id=str(advanced["candidate_id"]),
                        topic_name="模型优化",
                        reason="适合作为进阶阅读。",
                    )
                ],
            )

    app.dependency_overrides[get_zhihu_client] = FakeZhihuClient
    app.dependency_overrides[get_ai_client] = FakeAiClient
    try:
        response = client.post(
            "/api/routes/generate",
            json={
                "url": "https://www.zhihu.com/question/123456/answer/987654"
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["source"]["content_type"] == "zhihu"
    assert len(data["route"]["prerequisite"]) == 1
    assert len(data["route"]["current"]) == 1
    assert len(data["route"]["advanced"]) == 1
    assert len(data["route"]["prerequisite"][0]["materials"]) == 1
    assert len(data["route"]["advanced"][0]["materials"]) == 1
    assert data["route"]["current"][0]["materials"][0]["is_mock"] is False
    assert all(
        not material["is_mock"]
        for material in data["route"]["prerequisite"][0]["materials"]
    )
    assert "由 AI 分析" in data["notice"]


def test_generate_route_rejects_non_zhihu_url() -> None:
    response = client.post(
        "/api/routes/generate",
        json={"url": "https://example.com/article"},
    )

    assert response.status_code == 422


def test_generate_route_rejects_invalid_url() -> None:
    response = client.post(
        "/api/routes/generate",
        json={"url": "not-a-url"},
    )

    assert response.status_code == 422


def test_generate_route_reports_unsupported_article() -> None:
    response = client.post(
        "/api/routes/generate",
        json={"url": "https://zhuanlan.zhihu.com/p/123456"},
    )

    assert response.status_code == 400
    assert "文章详情能力尚未确认" in response.json()["detail"]


def test_zhihu_search_endpoint_uses_adapter() -> None:
    class FakeZhihuClient:
        async def search(
            self,
            query: str,
            count: int,
            sort_by: str | None,
        ) -> dict[str, list[dict[str, str]]]:
            assert query == "AI Agent"
            assert count == 3
            assert sort_by is None
            return {"Items": [{"Title": "Mocked API item"}]}

    app.dependency_overrides[get_zhihu_client] = FakeZhihuClient
    try:
        response = client.post(
            "/api/zhihu/search",
            json={"query": "AI Agent", "count": 3},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "query": "AI Agent",
        "data": {"Items": [{"Title": "Mocked API item"}]},
    }
