"""
매매일지 API
- 매매 기록 추가 / 조회 / 삭제
"""
from datetime import datetime, timezone
from typing import List

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_current_user
from app.db.mongo import get_db
from app.schemas.stock import TradeLogCreate, TradeLogItem

router = APIRouter(prefix="/trade-log", tags=["trade-log"])


def _db() -> AsyncIOMotorDatabase:
    return get_db()


@router.post("", response_model=TradeLogItem, status_code=201, summary="매매 기록 추가")
async def create_trade_log(
    body: TradeLogCreate,
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    """매수/매도 거래 기록 추가"""
    doc = {
        "user_id": str(current_user["_id"]),
        "stock_code": body.stock_code,
        "stock_name": body.stock_name,
        "trade_type": body.trade_type,
        "price": body.price,
        "quantity": body.quantity,
        "total_amount": body.price * body.quantity,
        "memo": body.memo,
        "traded_at": datetime.now(timezone.utc),
    }
    result = await db.trade_logs.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return TradeLogItem(**{**doc, "id": str(result.inserted_id)})


@router.get("", response_model=List[TradeLogItem], summary="매매 기록 조회")
async def get_trade_logs(
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    """현재 로그인 사용자의 매매 기록 조회"""
    cursor = db.trade_logs.find(
        {"user_id": str(current_user["_id"])}
    ).sort("traded_at", -1)

    result = []
    async for doc in cursor:
        result.append(TradeLogItem(
            id=str(doc["_id"]),
            stock_code=doc["stock_code"],
            stock_name=doc["stock_name"],
            trade_type=doc["trade_type"],
            price=doc["price"],
            quantity=doc["quantity"],
            total_amount=doc["total_amount"],
            memo=doc.get("memo"),
            traded_at=doc["traded_at"],
        ))
    return result


@router.delete("/{log_id}", status_code=204, summary="매매 기록 삭제")
async def delete_trade_log(
    log_id: str,
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    """매매 기록 삭제 (본인 기록만)"""
    try:
        oid = ObjectId(log_id)
    except Exception:
        raise HTTPException(status_code=400, detail="잘못된 ID 형식입니다.")

    result = await db.trade_logs.delete_one({
        "_id": oid,
        "user_id": str(current_user["_id"])
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
