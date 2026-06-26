from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.db.mongo import get_db

router = APIRouter(prefix="/subscription", tags=["subscription"])

VALID_PLANS = {"basic-plan", "ju-model", "seo-model", "auto-trade", "telegram"}


class SubscribeRequest(BaseModel):
    plan_id: str


class SubscribeResponse(BaseModel):
    message: str
    plan: str
    subscribed_at: str


def db_dep() -> AsyncIOMotorDatabase:
    return get_db()


@router.post("", response_model=SubscribeResponse, summary="플랜 구독/변경")
async def subscribe(
    body: SubscribeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(db_dep),
):
    """
    플랜 구독 또는 변경.
    PG 연동 전 단계로 결제 완료로 간주하고 플랜을 즉시 적용합니다.
    """
    if body.plan_id not in VALID_PLANS:
        raise HTTPException(status_code=400, detail="유효하지 않은 플랜입니다.")

    now = datetime.now(timezone.utc)

    await db.users.update_one(
        {"_id": current_user["_id"]},
        {
            "$set": {
                "plan": body.plan_id,
                "plan_subscribed_at": now,
                "updated_at": now,
            }
        },
    )

    # 구독 이력 저장
    await db.subscription_history.insert_one({
        "user_id": str(current_user["_id"]),
        "email": current_user["email"],
        "plan": body.plan_id,
        "subscribed_at": now,
        "status": "active",
    })

    return SubscribeResponse(
        message="플랜이 변경되었습니다.",
        plan=body.plan_id,
        subscribed_at=now.isoformat(),
    )


@router.get("", summary="현재 구독 정보 조회")
async def get_subscription(current_user: dict = Depends(get_current_user)):
    return {
        "plan": current_user.get("plan", "basic-plan"),
        "subscribed_at": current_user.get("plan_subscribed_at", None),
    }


@router.delete("", summary="구독 해지 (기본 플랜으로 변경)")
async def cancel_subscription(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(db_dep),
):
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"plan": "basic-plan", "updated_at": now}},
    )
    return {"message": "구독이 해지되었습니다. 기본 플랜으로 변경됩니다."}
