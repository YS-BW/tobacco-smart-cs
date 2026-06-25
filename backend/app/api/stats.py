"""统计接口。"""

from fastapi import APIRouter

from app.models.schemas import ApiResponse
from app.services import stats_service

router = APIRouter()


@router.get("/stats/overview")
async def stats_overview():
    """统计总览：总会话数、总消息数、文档数、命中率。"""
    data = await stats_service.get_overview()
    return ApiResponse(data=data)


@router.get("/stats/top-questions")
async def top_questions(limit: int = 10, days: int = 7):
    """热门问题 Top N。"""
    data = await stats_service.get_top_questions(limit=limit, days=days)
    return ApiResponse(data=data)
