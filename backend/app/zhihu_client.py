"""Small client for the Zhihu Open Platform endpoints supplied by the user."""

import os
import re
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()


class ZhihuApiError(RuntimeError):
    """A safe, normalized error raised for Zhihu API failures."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class ZhihuClient:
    """Call the documented Zhihu search endpoint with server-side credentials."""

    base_url = "https://developer.zhihu.com/api/v1"

    def __init__(
        self,
        access_secret: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.access_secret = access_secret or os.getenv("ZHIHU_ACCESS_SECRET")
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        if not self.access_secret:
            raise ZhihuApiError(
                "缺少 ZHIHU_ACCESS_SECRET，请在 backend/.env 中配置。"
            )
        return {
            "Authorization": f"Bearer {self.access_secret}",
            "X-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        }

    async def _get(
        self,
        path: str,
        params: dict[str, str | int | None],
    ) -> Any:
        query = {
            key: value
            for key, value in params.items()
            if value is not None and value != ""
        }
        try:
            async with httpx.AsyncClient(
                timeout=60,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    f"{self.base_url}{path}",
                    params=query,
                    headers=self._headers(),
                )
        except httpx.HTTPError as error:
            raise ZhihuApiError(f"请求知乎 API 失败：{error}") from error

        try:
            body = response.json()
        except ValueError as error:
            raise ZhihuApiError(
                f"知乎 API 返回了无法解析的响应（HTTP {response.status_code}）。",
                status=response.status_code,
            ) from error

        if not isinstance(body, dict):
            raise ZhihuApiError("知乎 API 返回结构不是 JSON 对象。")
        if response.status_code >= 400 or body.get("Code") != 0:
            raise ZhihuApiError(
                body.get("Message") or f"知乎 API 请求失败（HTTP {response.status_code}）。",
                code=body.get("Code") if isinstance(body.get("Code"), int) else None,
                status=response.status_code,
            )
        return body.get("Data", {})

    async def search(
        self,
        query: str,
        count: int = 5,
        sort_by: str | None = None,
    ) -> Any:
        """Search Zhihu questions, answers, and articles."""

        normalized_query = query.strip()
        if not normalized_query:
            raise ZhihuApiError("搜索关键词不能为空。")
        if sort_by:
            validate_sort_by(sort_by)
        return await self._get(
            "/content/zhihu_search",
            {
                "Query": normalized_query,
                "Count": min(max(count, 1), 10),
                "SortBy": sort_by,
            },
        )

    async def question_answers(
        self,
        question_url: str,
        offset: int = 0,
        count: int = 20,
    ) -> Any:
        """Fetch answer summaries for a complete Zhihu question URL."""

        normalized_url = question_url.strip()
        if not normalized_url:
            raise ZhihuApiError("问题链接不能为空。")
        return await self._get(
            "/content/question_answers",
            {
                "QuestionUrl": normalized_url,
                "Offset": max(offset, 0),
                "Limit": min(max(count, 1), 50),
            },
        )


def validate_sort_by(sort_by: str) -> None:
    """Validate the sort expressions supported by the supplied API client."""

    pattern = re.compile(
        r"^(CommentCount|VoteUpCount|EditTime)(?::(asc|desc))?(?::\(([^()]*)\))?$",
        re.IGNORECASE,
    )
    if not pattern.fullmatch(sort_by.strip()):
        raise ZhihuApiError(
            "sort_by 无效，只支持 CommentCount、VoteUpCount、EditTime，"
            "例如 VoteUpCount:desc。"
        )
