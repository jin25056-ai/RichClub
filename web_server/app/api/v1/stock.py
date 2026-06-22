"""
주식 관련 API
- AI 예측 목록 (매수/매도/관망 태그)
- RSI 차트 데이터
- MACD 차트 데이터
- 5분봉 차트 데이터
- 종목 리스트 / 검색
- AI 분석 상세 (매수 근거)
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.db.mongo import get_db
from app.schemas.stock import (
    AIPredictionItem,
    AIDetailResponse,
    MACDResponse, MACDDataPoint,
    RSIResponse, RSIDataPoint,
    StockItem,
    StockSearchResult,
)

router = APIRouter(prefix="/stock", tags=["stock"])

SIGNAL_MAP = {0: "매도", 1: "매수", 2: "관망"}
PERIOD_DAYS = {"1m": 30, "3m": 90, "6m": 180}

CONDITION_LABELS = {
    "cond_yang_bong":         "양봉 (종가 > 시가)",
    "cond_ma5_20_gc":         "5일선/20일선 골든크로스",
    "cond_ma60_filter":       "60일선 위 또는 상향 돌파",
    "cond_macd_total":        "MACD 정배열 및 상승 중",
    "cond_stoch_pure":        "스토캐스틱 K선 > D선",
    "cond_obv_rising":        "OBV 상승 (거래량 수반)",
    "cond_sp500_bear_market": "S&P500 하락장 아님",
    "watch_signal":           "관망 4대 요건 충족",
}


def _db() -> AsyncIOMotorDatabase:
    return get_db()


# ── 5분봉 스키마 ───────────────────────────────────────────────────────────────
class CandleDataPoint(BaseModel):
    datetime: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]


class CandleResponse(BaseModel):
    stock_code: str
    interval: str
    data: List[CandleDataPoint]


# ── 종목 리스트 ────────────────────────────────────────────────────────────────
@router.get("/list", response_model=List[StockItem], summary="종목 리스트")
async def get_stock_list(
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    cursor = db.stock_ohlcv.aggregate([
        {"$group": {"_id": "$stock_code", "stock_name": {"$first": "$stock_name"}}},
        {"$sort": {"_id": 1}},
    ])
    result = []
    async for doc in cursor:
        result.append(StockItem(stock_code=doc["_id"], stock_name=doc.get("stock_name", "")))
    return result


# ── 종목 검색 ──────────────────────────────────────────────────────────────────
@router.get("/search", response_model=List[StockSearchResult], summary="종목 검색")
async def search_stock(
    q: str = Query(..., description="종목코드 또는 종목명 검색어"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    cursor = db.stock_ohlcv.aggregate([
        {
            "$match": {
                "$or": [
                    {"stock_code": {"$regex": q, "$options": "i"}},
                    {"stock_name": {"$regex": q, "$options": "i"}},
                ]
            }
        },
        {"$group": {"_id": "$stock_code", "stock_name": {"$first": "$stock_name"}}},
        {"$sort": {"_id": 1}},
        {"$limit": 20},
    ])
    result = []
    async for doc in cursor:
        result.append(StockSearchResult(stock_code=doc["_id"], stock_name=doc.get("stock_name", "")))
    return result


# ── AI 예측 목록 ───────────────────────────────────────────────────────────────
@router.get("/ai/predictions", response_model=List[AIPredictionItem], summary="AI 예측 목록")
async def get_ai_predictions(
    signal: Optional[str] = Query(None, description="매수 / 매도 / 관망 필터"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    query: dict = {}
    if signal in ("매수", "매도", "관망"):
        query["signal"] = signal

    cursor = db.total_trading_signals.find(query).sort("predicted_at", -1).limit(limit)
    result = []
    async for doc in cursor:
        signal_str = doc.get("signal", "관망")
        signal_label = {v: k for k, v in SIGNAL_MAP.items()}.get(signal_str, 2)
        result.append(AIPredictionItem(
            stock_code=doc.get("stock_code", ""),
            stock_name=doc.get("stock_name", ""),
            current_price=doc.get("close"),
            signal=signal_str,
            signal_label=signal_label,
            confidence=doc.get("confidence"),
            predicted_at=doc.get("predicted_at"),
        ))
    return result


# ── AI 분석 상세 ───────────────────────────────────────────────────────────────
@router.get("/ai/detail/{stock_code}", response_model=AIDetailResponse, summary="AI 분석 상세")
async def get_ai_detail(
    stock_code: str,
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    doc = await db.total_trading_signals.find_one(
        {"stock_code": stock_code},
        sort=[("predicted_at", -1)]
    )
    if not doc:
        raise HTTPException(status_code=404, detail="해당 종목의 AI 예측 결과가 없습니다.")

    feature_importance = doc.get("feature_importance", [])
    if not feature_importance:
        fi_fields = ["macd", "stoch_k", "stoch_d", "obv", "ma5_20_ratio",
                     "ma20_60_ratio", "close_ma60_ratio", "vix_value"]
        for f in fi_fields:
            if f in doc:
                feature_importance.append({
                    "feature": f,
                    "value": round(float(doc[f]), 4) if doc[f] is not None else None,
                    "direction": "positive" if doc.get(f, 0) > 0 else "negative"
                })

    return AIDetailResponse(
        stock_code=stock_code,
        stock_name=doc.get("stock_name", ""),
        signal=doc.get("signal", "관망"),
        confidence=doc.get("confidence"),
        feature_importance=feature_importance,
        conditions_met=doc.get("conditions_met", []),
        conditions_not_met=doc.get("conditions_not_met", []),
        predicted_at=doc.get("predicted_at"),
    )


# ── RSI 차트 ───────────────────────────────────────────────────────────────────
@router.get("/chart/rsi/{stock_code}", response_model=RSIResponse, summary="RSI 차트 데이터")
async def get_rsi(
    stock_code: str,
    period: str = Query("3m", description="기간: 1m / 3m / 6m"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    if period not in PERIOD_DAYS:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m 중 하나여야 합니다.")

    days = PERIOD_DAYS[period]
    since = datetime.utcnow() - timedelta(days=days + 20)

    cursor = db.stock_ohlcv.find(
        {"stock_code": stock_code, "date": {"$gte": since}},
        {"date": 1, "close": 1, "stock_name": 1, "_id": 0}
    ).sort("date", 1)

    docs = [doc async for doc in cursor]
    if not docs:
        raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name", "")
    closes = [float(d["close"]) for d in docs]
    dates = [d["date"].strftime("%Y-%m-%d") if hasattr(d["date"], "strftime") else str(d["date"]) for d in docs]
    rsi_values = _calc_rsi(closes, window=14)

    cutoff = datetime.utcnow() - timedelta(days=days)
    data = []
    for i, d in enumerate(docs):
        dt = d["date"]
        dt_naive = dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt
        if dt_naive >= cutoff and rsi_values[i] is not None:
            data.append(RSIDataPoint(date=dates[i], rsi=round(rsi_values[i], 2)))

    return RSIResponse(stock_code=stock_code, stock_name=stock_name, period=period, data=data)


# ── MACD 차트 ──────────────────────────────────────────────────────────────────
@router.get("/chart/macd/{stock_code}", response_model=MACDResponse, summary="MACD 차트 데이터")
async def get_macd(
    stock_code: str,
    period: str = Query("3m", description="기간: 1m / 3m / 6m"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    if period not in PERIOD_DAYS:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m 중 하나여야 합니다.")

    days = PERIOD_DAYS[period]
    since = datetime.utcnow() - timedelta(days=days + 40)

    cursor = db.stock_ohlcv.find(
        {"stock_code": stock_code, "date": {"$gte": since}},
        {"date": 1, "close": 1, "stock_name": 1, "_id": 0}
    ).sort("date", 1)

    docs = [doc async for doc in cursor]
    if not docs:
        raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name", "")
    closes = [float(d["close"]) for d in docs]
    dates = [d["date"].strftime("%Y-%m-%d") if hasattr(d["date"], "strftime") else str(d["date"]) for d in docs]
    macd_line, signal_line, histogram = _calc_macd(closes)

    cutoff = datetime.utcnow() - timedelta(days=days)
    data = []
    for i, d in enumerate(docs):
        dt = d["date"]
        dt_naive = dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt
        if dt_naive >= cutoff and macd_line[i] is not None:
            data.append(MACDDataPoint(
                date=dates[i],
                macd=round(macd_line[i], 4),
                signal=round(signal_line[i], 4),
                histogram=round(histogram[i], 4),
            ))

    return MACDResponse(stock_code=stock_code, stock_name=stock_name, period=period, data=data)


# ── 5분봉 차트 ─────────────────────────────────────────────────────────────────
@router.get("/chart/candle/{stock_code}", response_model=CandleResponse, summary="5분봉 차트 데이터")
async def get_candles(
    stock_code: str,
    days: int = Query(1, ge=1, le=30, description="조회 일수 (최대 30일)"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """
    종목별 5분봉 데이터 반환
    candles_5m 컬렉션에서 조회 (스케줄러가 장 중 5분마다 누적 수집)
    """
    since = datetime.utcnow() - timedelta(days=days)

    cursor = db.candles_5m.find(
        {"stock_code": stock_code, "datetime": {"$gte": since}},
        {"_id": 0, "datetime": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    ).sort("datetime", 1)

    docs = [doc async for doc in cursor]
    if not docs:
        raise HTTPException(status_code=404, detail="5분봉 데이터가 없습니다. 장 중에 수집됩니다.")

    data = []
    for d in docs:
        dt = d["datetime"]
        dt_str = dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)
        data.append(CandleDataPoint(
            datetime=dt_str,
            open=d.get("open"),
            high=d.get("high"),
            low=d.get("low"),
            close=d.get("close"),
            volume=d.get("volume"),
        ))

    return CandleResponse(stock_code=stock_code, interval="5m", data=data)


# ── 내부 계산 함수 ─────────────────────────────────────────────────────────────
def _calc_rsi(closes: list, window: int = 14) -> list:
    rsi = [None] * len(closes)
    if len(closes) < window + 1:
        return rsi

    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:window]) / window
    avg_loss = sum(losses[:window]) / window

    for i in range(window, len(closes)):
        if i > window:
            avg_gain = (avg_gain * (window - 1) + gains[i - 1]) / window
            avg_loss = (avg_loss * (window - 1) + losses[i - 1]) / window
        rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
        rsi[i] = 100 - (100 / (1 + rs))

    return rsi


def _calc_macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9):
    def ema(data, span):
        result = [None] * len(data)
        k = 2 / (span + 1)
        for i, v in enumerate(data):
            result[i] = v if i == 0 else v * k + result[i - 1] * (1 - k)
        return result

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [(f - s) if f is not None and s is not None else None for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema([v if v is not None else 0 for v in macd_line], signal)
    histogram = [(m - s) if m is not None else None for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram
