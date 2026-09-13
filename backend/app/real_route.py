"""Build an AI-planned learning route using only real Zhihu materials."""

import math
import re
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from app.ai_client import AiClient
from app.models import (
    GenerateRouteRequest,
    GenerateRouteResponse,
    KnowledgeAnalysis,
    KnowledgeTopic,
    LearningMaterial,
    LearningRoute,
    MaterialChoice,
    MaterialSelection,
    RouteStep,
    SourceContent,
)
from app.zhihu_client import ZhihuApiError, ZhihuClient

QUESTION_PATH = re.compile(r"^/question/(?P<question_id>\d+)(?:/answer/(?P<answer_id>\d+))?/?$")


async def build_real_route(
    request: GenerateRouteRequest,
    zhihu_client: ZhihuClient,
    ai_client: AiClient,
) -> GenerateRouteResponse:
    """Resolve source, plan knowledge nodes, retrieve, then constrain selection."""

    submitted_url = str(request.url)
    match = QUESTION_PATH.match(urlsplit(submitted_url).path)
    if not match:
        raise ValueError(
            "当前流程仅支持知乎问题或回答链接；文章详情能力尚未确认。"
        )

    question_url = f"https://www.zhihu.com/question/{match.group('question_id')}"
    target_answer_id = match.group("answer_id")
    answers = await _fetch_answers(zhihu_client, question_url, target_answer_id)
    source_item = _select_source_answer(answers, target_answer_id)
    source_text = _text(source_item.get("Summary"))
    if not source_text:
        raise ZhihuApiError("目标知乎内容没有可供 AI 分析的摘要。")

    analysis = await ai_client.analyze_content(source_text)
    candidates = await _search_candidates(
        zhihu_client,
        analysis,
        submitted_url,
    )
    if not candidates:
        raise ZhihuApiError("没有搜索到可供筛选的真实知乎资料。")

    selection = await ai_client.select_materials(
        analysis,
        [_candidate_for_ai(item) for item in candidates],
    )
    candidate_by_id = {item["candidate_id"]: item for item in candidates}
    prerequisite_steps = _build_steps(
        analysis.prerequisites,
        selection.prerequisites,
        candidate_by_id,
        "入门",
    )
    advanced_steps = _build_steps(
        analysis.advanced_topics,
        selection.advanced,
        candidate_by_id,
        "进阶",
    )

    source_type = "回答" if target_answer_id else "问题"
    return GenerateRouteResponse(
        source=SourceContent(
            url=request.url,
            title=analysis.title,
            summary=analysis.summary,
            content_type="zhihu",
        ),
        route=LearningRoute(
            prerequisite=prerequisite_steps,
            current=[
                RouteStep(
                    title=f"当前知识：{analysis.title}",
                    description=(
                        f"难度判断：{analysis.current_level}。核心概念："
                        + "、".join(analysis.core_concepts)
                    ),
                    difficulty=analysis.current_level,
                    materials=[
                        LearningMaterial(
                            title=f"用户提交的知乎{source_type}",
                            reason="这是本次知识分析和路线规划的起点。",
                            url=request.url,
                            is_mock=False,
                        )
                    ],
                )
            ],
            advanced=advanced_steps,
        ),
        notice="知识结构由 AI 分析；所有推荐资料均来自知乎 API 搜索结果。",
    )


async def _search_candidates(
    client: ZhihuClient,
    analysis: KnowledgeAnalysis,
    submitted_url: str,
) -> list[dict[str, Any]]:
    jobs = [
        ("prerequisite", topic)
        for topic in analysis.prerequisites
    ] + [
        ("advanced", topic)
        for topic in analysis.advanced_topics
    ]
    candidates: list[dict[str, Any]] = []
    seen_urls = {_without_query(submitted_url)}
    # Search sequentially. A route can contain several topics and sending all
    # searches in one burst can trigger the Open Platform rate limiter.
    for stage, topic in jobs:
        data = await client.search(topic.search_query, 10, "VoteUpCount:desc")
        if not isinstance(data, dict) or not isinstance(data.get("Items"), list):
            continue
        topic_candidates: list[dict[str, Any]] = []
        topic_seen: set[str] = set()
        for item in data["Items"]:
            candidate = _normalize_candidate(item, stage, topic.name)
            if (
                not candidate
                or candidate["normalized_url"] in seen_urls
                or candidate["normalized_url"] in topic_seen
            ):
                continue
            topic_seen.add(candidate["normalized_url"])
            topic_candidates.append(candidate)
        selected = sorted(
            topic_candidates,
            key=lambda item: item["quality_score"],
            reverse=True,
        )[:5]
        candidates.extend(selected)
        seen_urls.update(
            candidate["normalized_url"] for candidate in selected
        )
    return candidates


def _normalize_candidate(
    item: Any,
    stage: str,
    topic_name: str,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    title, url = _text(item.get("Title")), _text(item.get("Url"))
    if not title or not url or not _is_zhihu_url(url):
        return None
    votes = _number(item.get("VoteUpCount"))
    comments = _number(item.get("CommentCount"))
    authority = _number(item.get("AuthorityLevel"))
    ranking = _number(item.get("RankingScore"))
    excerpt = _text(item.get("ContentText"))[:700]
    quality_score = (
        ranking * 3
        + math.log1p(max(votes, 0))
        + math.log1p(max(comments, 0)) * 0.4
        + authority * 0.25
        + min(len(excerpt) / 700, 1)
    )
    return {
        "candidate_id": _text(item.get("ContentID")) or _without_query(url),
        "title": title,
        "url": url,
        "normalized_url": _without_query(url),
        "excerpt": excerpt,
        "content_type": _text(item.get("ContentType")),
        "vote_count": int(votes),
        "comment_count": int(comments),
        "authority_level": authority,
        "ranking_score": ranking,
        "quality_score": quality_score,
        "stage": stage,
        "topic_name": topic_name,
    }


def _candidate_for_ai(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: candidate[key]
        for key in (
            "candidate_id",
            "title",
            "excerpt",
            "content_type",
            "vote_count",
            "comment_count",
            "authority_level",
            "ranking_score",
            "stage",
            "topic_name",
        )
    }


def _build_steps(
    topics: list[KnowledgeTopic],
    choices: list[MaterialChoice],
    candidates: dict[str, dict[str, Any]],
    difficulty: Literal["入门", "基础", "进阶"],
) -> list[RouteStep]:
    used: set[str] = set()
    steps: list[RouteStep] = []
    for topic in topics:
        materials: list[LearningMaterial] = []
        for choice in choices:
            candidate = candidates.get(choice.candidate_id)
            if (
                choice.topic_name != topic.name
                or not candidate
                or candidate["candidate_id"] in used
                or candidate["topic_name"] != topic.name
            ):
                continue
            used.add(candidate["candidate_id"])
            materials.append(
                LearningMaterial(
                    title=candidate["title"],
                    url=candidate["url"],
                    reason=choice.reason,
                    is_mock=False,
                )
            )
            if len(materials) == 2:
                break
        if not materials:
            fallback = next(
                (
                    item
                    for item in candidates.values()
                    if item["topic_name"] == topic.name
                    and item["candidate_id"] not in used
                ),
                None,
            )
            if fallback:
                used.add(fallback["candidate_id"])
                materials.append(
                    LearningMaterial(
                        title=fallback["title"],
                        url=fallback["url"],
                        reason="与该知识点相关，且综合质量指标在候选中靠前。",
                        is_mock=False,
                    )
                )
        if materials:
            steps.append(
                RouteStep(
                    title=topic.name,
                    description=f"{topic.description} 推荐原因：{topic.reason}",
                    difficulty=difficulty,
                    materials=materials,
                )
            )
    if not steps:
        raise ZhihuApiError("AI 没有从真实候选中选出有效资料。")
    return steps


async def _fetch_answers(
    client: ZhihuClient,
    question_url: str,
    target_answer_id: str | None,
) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    offset = 0
    for _ in range(3):
        data = await client.question_answers(question_url, offset=offset, count=20)
        if not isinstance(data, dict):
            break
        items = data.get("Items")
        if isinstance(items, list):
            answers.extend(item for item in items if isinstance(item, dict))
        if target_answer_id and any(
            str(item.get("ContentToken")) == target_answer_id for item in answers
        ):
            break
        paging = data.get("Paging")
        if not isinstance(paging, dict) or paging.get("IsEnd") is True:
            break
        next_offset = paging.get("NextOffset")
        if not isinstance(next_offset, int) or next_offset <= offset:
            break
        offset = next_offset
    if not answers:
        raise ZhihuApiError("知乎 API 没有返回可用于分析的回答摘要。")
    return answers


def _select_source_answer(
    answers: list[dict[str, Any]],
    target_answer_id: str | None,
) -> dict[str, Any]:
    if target_answer_id:
        for item in answers:
            if str(item.get("ContentToken")) == target_answer_id:
                return item
        raise ZhihuApiError("在知乎 API 返回的回答分页中没有找到目标回答。")
    return answers[0]


def _without_query(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def _is_zhihu_url(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host == "zhihu.com" or host.endswith(".zhihu.com")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0
