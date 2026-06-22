"""
관심종목 API
- 관심종목 추가 / 조회 / 삭제
- 로그인한 유저별로 관리
"""
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.db.mongo import get_db

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _db() -> AsyncIOMotorDatabase:
    return get_db()


# ── 스키마 ─────────────────────────────────────────────────────────────────────

class WatchlistAddRequest(BaseModel):
    stock_code: str
    stock_name: str
    memo: Optional[str] = None


class WatchlistItem(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    memo: Optional[str] = None
    added_at: datetime
    # AI 예측 정보 (total_trading_signals에서 join)
    signal: Optional[str] = None
    confidence: Optional[float] = None
    current_price: Optional[float] = None


# ── 관심종목 추가 ──────────────────────────────────────────────────────────────
@router.post("", response_model=WatchlistItem, status_code=201, summary="관심종목 추가")
async def add_watchlist(
    body: WatchlistAddRequest,
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["_id"])

    # 중복 체크
    existing = await db.watchlist.find_one({
        "user_id": user_id,
        "stock_code": body.stock_code
    })
    if existing:
        raise HTTPException(status_code=409, detail="이미 관심종목에 추가된 종목입니다.")

    doc = {
        "user_id": user_id,
        "stock_code": body.stock_code,
        "stock_name": body.stock_name,
        "memo": body.memo,
        "added_at": datetime.now(timezone.utc),
    }
    result = await db.watchlist.insert_one(doc)

    return WatchlistItem(
        id=str(result.inserted_id),
        stock_code=doc["stock_code"],
        stock_name=doc["stock_name"],
        memo=doc.get("memo"),
        added_at=doc["added_at"],
    )


# ── 관심종목 조회 ──────────────────────────────────────────────────────────────
@router.get("", response_model=List[WatchlistItem], summary="관심종목 조회")
async def get_watchlist(
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    """
    로그인한 유저의 관심종목 목록 조회
    각 종목의 최신 AI 예측 신호/신뢰도/현재가도 함께 반환
    """
    user_id = str(current_user["_id"])

    cursor = db.watchlist.find({"user_id": user_id}).sort("added_at", -1)
    items = [doc async for doc in cursor]

    if not items:
        return []

    # 종목코드 목록으로 AI 예측 정보 일괄 조회
    stock_codes = [item["stock_code"] for item in items]
    signal_map = {}

    # 각 종목의 최신 예측 1건씩
    pipeline = [
        {"$match": {"stock_code": {"$in": stock_codes}}},
        {"$sort": {"predicted_at": -1}},
        {"$group": {
            "_id": "$stock_code",
            "signal": {"$first": "$signal"},
            "confidence": {"$first": "$confidence"},
            "close": {"$first": "$close"},
        }},
    ]
    async for doc in db.total_trading_signals.aggregate(pipeline):
        signal_map[doc["_id"]] = doc

    result = []
    for item in items:
        sc = item["stock_code"]
        sig_info = signal_map.get(sc, {})
        result.append(WatchlistItem(
            id=str(item["_id"]),
            stock_code=sc,
            stock_name=item["stock_name"],
            memo=item.get("memo"),
            added_at=item["added_at"],
            signal=sig_info.get("signal"),
            confidence=sig_info.get("confidence"),
            current_price=sig_info.get("close"),
        ))

    return result


# ── 관심종목 삭제 ──────────────────────────────────────────────────────────────
@router.delete("/{item_id}", status_code=204, summary="관심종목 삭제")
async def delete_watchlist(
    item_id: str,
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    """관심종목 삭제 (본인 것만)"""
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="잘못된 ID 형식입니다.")

    result = await db.watchlist.delete_one({
        "_id": oid,
        "user_id": str(current_user["_id"])
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="관심종목을 찾을 수 없습니다.")


# ── 관심종목 여부 확인 ─────────────────────────────────────────────────────────
@router.get("/check/{stock_code}", summary="관심종목 여부 확인")
async def check_watchlist(
    stock_code: str,
    db: AsyncIOMotorDatabase = Depends(_db),
    current_user: dict = Depends(get_current_user),
):
    """특정 종목이 관심종목에 있는지 확인"""
    doc = await db.watchlist.find_one({
        "user_id": str(current_user["_id"]),
        "stock_code": stock_code
    })
    return {"is_watching": doc is not None, "id": str(doc["_id"]) if doc else None}
