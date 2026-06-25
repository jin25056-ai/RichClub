"""
네이버 뉴스 검색 API 프록시
"""
import httpx
from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", summary="주식 뉴스 검색")
async def get_news(
    query: str = Query(default="주식 증권"),
    display: int = Query(default=10, le=100),
    _: dict = Depends(get_current_user),
):
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {"query": query, "display": display, "sort": "date"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        return resp.json()
