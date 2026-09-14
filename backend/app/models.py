"""API data models for health checks and the learning-route workflow."""

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, HttpUrl, model_validator


class HealthResponse(BaseModel):
    """Response returned by the health-check endpoint."""

    status: Literal["ok"] = "ok"
    service: str = "zhihu-knowledge-agent"


class GenerateRouteRequest(BaseModel):
    """A supported Zhihu URL submitted by the user."""

    url: HttpUrl

    @model_validator(mode="after")
    def validate_zhihu_url(self) -> Self:
        """Reject non-Zhihu hosts before the workflow starts."""

        host = self.url.host.lower() if self.url.host else ""
        if host != "zhihu.com" and not host.endswith(".zhihu.com"):
            raise ValueError("url must point to zhihu.com")
        return self


class SourceContent(BaseModel):
    """Normalized information about the submitted source content."""

    url: HttpUrl
    title: str
    summary: str
    content_type: Literal["mock", "zhihu"] = "mock"


class LearningMaterial(BaseModel):
    """A learning resource attached to one route step."""

    title: str
    reason: str
    url: HttpUrl | None = None
    is_mock: bool = True


class RouteStep(BaseModel):
    """One knowledge step in a staged learning route."""

    title: str
    description: str
    difficulty: Literal["入门", "基础", "进阶"]
    materials: list[LearningMaterial]


class LearningRoute(BaseModel):
    """The prerequisite, current, and advanced sections of a route."""

    prerequisite: list[RouteStep]
    current: list[RouteStep]
    advanced: list[RouteStep]


class GenerateRouteResponse(BaseModel):
    """Stage 2 response containing an explicitly marked mock route."""

    source: SourceContent
    route: LearningRoute
    notice: str


class KnowledgeTopic(BaseModel):
    """A knowledge node and the query used to find real materials."""

    name: str
    description: str
    reason: str
    search_query: str


class KnowledgeAnalysis(BaseModel):
    """Structured analysis produced from the current Zhihu content."""

    title: str
    summary: str
    current_level: Literal["入门", "基础", "进阶"]
    core_concepts: list[str] = Field(min_length=1, max_length=6)
    prerequisites: list[KnowledgeTopic] = Field(min_length=1, max_length=3)
    advanced_topics: list[KnowledgeTopic] = Field(min_length=1, max_length=3)


class MaterialChoice(BaseModel):
    """One AI selection that must reference an existing candidate ID."""

    candidate_id: str
    topic_name: str
    reason: str


class MaterialSelection(BaseModel):
    """Selections for both sides of the learning route."""

    prerequisites: list[MaterialChoice]
    advanced: list[MaterialChoice]


class StageMaterialSelection(BaseModel):
    """AI choices for one streamed route stage."""

    choices: list[MaterialChoice]


class ZhihuSearchRequest(BaseModel):
    """Parameters accepted by the experimental Zhihu search endpoint."""

    query: str
    count: int = 5
    sort_by: str | None = None


class ZhihuSearchResponse(BaseModel):
    """Raw search data returned by the verified Zhihu API client."""

    query: str
    data: Any


class ZhihuQuestionAnswersRequest(BaseModel):
    """Parameters for retrieving answer summaries under one Zhihu question."""

    question_url: HttpUrl
    offset: int = 0
    count: int = 20


class ZhihuQuestionAnswersResponse(BaseModel):
    """Raw question-answer data returned by the Zhihu API."""

    question_url: HttpUrl
    data: Any
