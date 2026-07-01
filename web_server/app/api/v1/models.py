from fastapi import APIRouter, Depends
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/models", tags=["models"])

# 모델 정의 (추후 DB로 이관 가능)
ALL_MODELS = [
    {
        "id": "ju-model-v2",
        "name": "ju-model-v2",
        "description": "기본 AI 예측 모델",
        "required_plan": ["ju-model", "seo-model", "auto-trade"],
    },
    {
        "id": "seo-model-v1",
        "name": "seo-model-v1",
        "description": "고성능 AI 예측 모델 v1",
        "required_plan": ["seo-model", "auto-trade"],
    },
    {
        "id": "seo-model-v2",
        "name": "seo-model-v2",
        "description": "고성능 AI 예측 모델 v2",
        "required_plan": ["seo-model", "auto-trade"],
    },
]


@router.get("", summary="사용 가능한 모델 목록 조회")
async def get_models(current_user: dict = Depends(get_current_user)):
    """
    전체 모델 목록과 현재 유저의 플랜 기반 사용 가능 여부 반환.
    """
    user_plan = current_user.get("plan", "basic-plan")
    result = []
    for model in ALL_MODELS:
        result.append({
            "id": model["id"],
            "name": model["name"],
            "description": model["description"],
            "available": user_plan in model["required_plan"],
        })
    return result
