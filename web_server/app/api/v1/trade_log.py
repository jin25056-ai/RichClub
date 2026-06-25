"""
매매일지 API
- 매매 기록 추가 / 조회 / 소프트삭제 / 복구 / 수정
"""
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.db.mongo import get_db
from app.schemas.stock import TradeLogCreate, TradeLogItem

router = APIRouter(prefix="/trade-log", tags=["trade-log"])


def _db() -> AsyncIOMotorDatabase:
    return get_db()


class TradeLogUpdate(BaseModel):
    price: Optional[float] = None
    quantity: Optional[int] = None
    memo: Optional[str] = None
    traded_at: Optional[datetime] = None


@router.post("", response_model=TradeLogItem, status_code=201, summary="매매 기록 추가")
async def create_trade_log(
    body: TradeLogCreate,
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
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
        "deleted_at": None,
    }
    result = await db.trade_logs.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return TradeLogItem(**{**doc, "id": str(result.inserted_id)})


@router.get("", response_model=List[TradeLogItem], summary="매매 기록 조회")
async def get_trade_logs(
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    """삭제되지 않은 매매 기록만 반환"""
    cursor = db.trade_logs.find(
        {"user_id": str(current_user["_id"]), "deleted_at": None}
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


@router.get("/trash", response_model=List[TradeLogItem], summary="휴지통 조회")
async def get_trash(
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    """소프트 삭제된 기록 반환"""
    cursor = db.trade_logs.find(
        {"user_id": str(current_user["_id"]), "deleted_at": {"$ne": None}}
    ).sort("deleted_at", -1)

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


@router.patch("/{log_id}", response_model=TradeLogItem, summary="매매 기록 수정")
async def update_trade_log(
    log_id: str,
    body: TradeLogUpdate,
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(log_id)
    except Exception:
        raise HTTPException(status_code=400, detail="잘못된 ID 형식입니다.")

    update_fields: dict = {}
    if body.price is not None:
        update_fields["price"] = body.price
    if body.quantity is not None:
        update_fields["quantity"] = body.quantity
        if body.price is not None:
            update_fields["total_amount"] = body.price * body.quantity
    if body.memo is not None:
        update_fields["memo"] = body.memo
    if body.traded_at is not None:
        update_fields["traded_at"] = body.traded_at

    if not update_fields:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")

    result = await db.trade_logs.find_one_and_update(
        {"_id": oid, "user_id": str(current_user["_id"]), "deleted_at": None},
        {"$set": update_fields},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")

    return TradeLogItem(
        id=str(result["_id"]),
        stock_code=result["stock_code"],
        stock_name=result["stock_name"],
        trade_type=result["trade_type"],
        price=result["price"],
        quantity=result["quantity"],
        total_amount=result["total_amount"],
        memo=result.get("memo"),
        traded_at=result["traded_at"],
    )


@router.delete("/{log_id}", status_code=204, summary="매매 기록 소프트 삭제")
async def delete_trade_log(
    log_id: str,
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    """실제 삭제 대신 deleted_at 필드 설정 (휴지통 이동)"""
    try:
        oid = ObjectId(log_id)
    except Exception:
        raise HTTPException(status_code=400, detail="잘못된 ID 형식입니다.")

    result = await db.trade_logs.update_one(
        {"_id": oid, "user_id": str(current_user["_id"]), "deleted_at": None},
        {"$set": {"deleted_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")


@router.post("/{log_id}/restore", response_model=TradeLogItem, summary="휴지통에서 복구")
async def restore_trade_log(
    log_id: str,
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(log_id)
    except Exception:
        raise HTTPException(status_code=400, detail="잘못된 ID 형식입니다.")

    result = await db.trade_logs.find_one_and_update(
        {"_id": oid, "user_id": str(current_user["_id"]), "deleted_at": {"$ne": None}},
        {"$set": {"deleted_at": None}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")

    return TradeLogItem(
        id=str(result["_id"]),
        stock_code=result["stock_code"],
        stock_name=result["stock_name"],
        trade_type=result["trade_type"],
        price=result["price"],
        quantity=result["quantity"],
        total_amount=result["total_amount"],
        memo=result.get("memo"),
        traded_at=result["traded_at"],
    )


@router.delete("/{log_id}/permanent", status_code=204, summary="영구 삭제")
async def permanently_delete_trade_log(
    log_id: str,
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(log_id)
    except Exception:
        raise HTTPException(status_code=400, detail="잘못된 ID 형식입니다.")

    result = await db.trade_logs.delete_one(
        {"_id": oid, "user_id": str(current_user["_id"])}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
