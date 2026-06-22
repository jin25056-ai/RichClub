"""
주식 관련 API
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.db.mongo import get_db
from app.schemas.stock import (
    AIPredictionItem, AIDetailResponse,
    MACDResponse, MACDDataPoint,
    RSIResponse, RSIDataPoint,
    StockItem, StockSearchResult,
)

router = APIRouter(prefix="/stock", tags=["stock"])

SIGNAL_MAP = {0: "매도", 1: "매수", 2: "관망"}
PERIOD_DAYS = {"1m": 30, "3m": 90, "6m": 180}


def _db() -> AsyncIOMotorDatabase:
    return get_db()


class CandleDataPoint(BaseModel):
    datetime: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]
    ma5: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None


class CandleResponse(BaseModel):
    stock_code: str
    interval: str
    data: List[CandleDataPoint]


@router.get("/list", response_model=List[StockItem], summary="종목 리스트")
async def get_stock_list(db: AsyncIOMotorDatabase = Depends(_db), _: dict = Depends(get_current_user)):
    cursor = db.total_trading_signals.aggregate([
        {"$group": {"_id": "$stock_code", "stock_name": {"$first": "$stock_name"}}},
        {"$sort": {"_id": 1}},
    ])
    result = []
    async for doc in cursor:
        result.append(StockItem(stock_code=doc["_id"], stock_name=doc.get("stock_name", "")))
    return result


@router.get("/search", response_model=List[StockSearchResult], summary="종목 검색")
async def search_stock(
    q: str = Query(...), db: AsyncIOMotorDatabase = Depends(_db), _: dict = Depends(get_current_user)
):
    cursor = db.total_trading_signals.aggregate([
        {"$match": {"$or": [
            {"stock_code": {"$regex": q, "$options": "i"}},
            {"stock_name": {"$regex": q, "$options": "i"}},
        ]}},
        {"$group": {"_id": "$stock_code", "stock_name": {"$first": "$stock_name"}}},
        {"$sort": {"_id": 1}},
        {"$limit": 20},
    ])
    result = []
    async for doc in cursor:
        result.append(StockSearchResult(stock_code=doc["_id"], stock_name=doc.get("stock_name", "")))
    return result


@router.get("/ai/predictions", response_model=List[AIPredictionItem], summary="AI 예측 목록")
async def get_ai_predictions(
    signal: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    stock_name: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    query: dict = {}
    if signal in ("매수", "매도", "관망"):
        query["signal"] = signal
    if stock_name:
        query["stock_name"] = stock_name
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


@router.get("/ai/detail/{stock_code}", response_model=AIDetailResponse, summary="AI 분석 상세")
async def get_ai_detail(
    stock_code: str, db: AsyncIOMotorDatabase = Depends(_db), _: dict = Depends(get_current_user)
):
    doc = await db.total_trading_signals.find_one({"stock_code": stock_code}, sort=[("predicted_at", -1)])
    if not doc:
        raise HTTPException(status_code=404, detail="해당 종목의 AI 예측 결과가 없습니다.")

    feature_importance = doc.get("feature_importance", [])
    if not feature_importance:
        fi_fields = {"rsi": "RSI", "macd": "MACD", "stoch_k": "스토캐스틱 K", "stoch_d": "스토캐스틱 D",
                     "ma5_20_ratio": "5/20일선 비율", "ma20_60_ratio": "20/60일선 비율",
                     "close_ma60_ratio": "종가/60일선 비율", "vix_value": "VIX"}
        for f, label in fi_fields.items():
            if f in doc and doc[f] is not None:
                feature_importance.append({
                    "feature": label, "importance": None,
                    "value": round(float(doc[f]), 4),
                    "direction": "positive" if float(doc[f]) > 0 else "negative"
                })

    return AIDetailResponse(
        stock_code=stock_code, stock_name=doc.get("stock_name", ""),
        signal=doc.get("signal", "관망"), confidence=doc.get("confidence"),
        feature_importance=feature_importance,
        conditions_met=doc.get("conditions_met", []),
        conditions_not_met=doc.get("conditions_not_met", []),
        predicted_at=doc.get("predicted_at"),
    )


@router.get("/chart/rsi/{stock_code}", response_model=RSIResponse, summary="RSI 차트 데이터")
async def get_rsi(
    stock_code: str, period: str = Query("3m"),
    db: AsyncIOMotorDatabase = Depends(_db), _: dict = Depends(get_current_user)
):
    if period not in PERIOD_DAYS:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m 중 하나여야 합니다.")
    days = PERIOD_DAYS[period]
    since = datetime.utcnow() - timedelta(days=days + 20)
    cursor = db.total_trading_signals.find(
        {"stock_code": stock_code, "predicted_at": {"$gte": since}},
        {"predicted_at": 1, "close": 1, "rsi": 1, "stock_name": 1, "_id": 0}
    ).sort("predicted_at", 1)
    docs = [doc async for doc in cursor]
    if not docs:
        raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")
    stock_name = docs[0].get("stock_name", "")
    cutoff = datetime.utcnow() - timedelta(days=days)
    data = []
    has_rsi = any(d.get("rsi") is not None for d in docs)
    if has_rsi:
        for d in docs:
            dt = d["predicted_at"]
            dt_naive = dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt
            if dt_naive >= cutoff and d.get("rsi") is not None:
                data.append(RSIDataPoint(date=dt.strftime("%Y-%m-%d"), rsi=round(float(d["rsi"]), 2)))
    else:
        closes = [float(d["close"]) for d in docs if d.get("close")]
        dates = [d["predicted_at"] for d in docs if d.get("close")]
        rsi_values = _calc_rsi(closes)
        for i, dt in enumerate(dates):
            dt_naive = dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt
            if dt_naive >= cutoff and rsi_values[i] is not None:
                data.append(RSIDataPoint(date=dt.strftime("%Y-%m-%d"), rsi=round(rsi_values[i], 2)))
    return RSIResponse(stock_code=stock_code, stock_name=stock_name, period=period, data=data)


@router.get("/chart/macd/{stock_code}", response_model=MACDResponse, summary="MACD 차트 데이터")
async def get_macd(
    stock_code: str, period: str = Query("3m"),
    db: AsyncIOMotorDatabase = Depends(_db), _: dict = Depends(get_current_user)
):
    if period not in PERIOD_DAYS:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m 중 하나여야 합니다.")
    days = PERIOD_DAYS[period]
    since = datetime.utcnow() - timedelta(days=days + 40)
    cursor = db.total_trading_signals.find(
        {"stock_code": stock_code, "predicted_at": {"$gte": since}},
        {"predicted_at": 1, "close": 1, "macd": 1, "stock_name": 1, "_id": 0}
    ).sort("predicted_at", 1)
    docs = [doc async for doc in cursor]
    if not docs:
        raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")
    stock_name = docs[0].get("stock_name", "")
    cutoff = datetime.utcnow() - timedelta(days=days)
    closes = [float(d["close"]) for d in docs if d.get("close")]
    dates = [d["predicted_at"] for d in docs if d.get("close")]
    macd_line, signal_line, histogram = _calc_macd(closes)
    data = []
    for i, dt in enumerate(dates):
        dt_naive = dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt
        if dt_naive >= cutoff and macd_line[i] is not None:
            data.append(MACDDataPoint(
                date=dt.strftime("%Y-%m-%d"),
                macd=round(macd_line[i], 4),
                signal=round(signal_line[i], 4),
                histogram=round(histogram[i], 4),
            ))
    return MACDResponse(stock_code=stock_code, stock_name=stock_name, period=period, data=data)


@router.get("/chart/candle/{stock_code}", response_model=CandleResponse, summary="캔들 차트 데이터")
async def get_candles(
    stock_code: str,
    days: int = Query(30, ge=1, le=240),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    since = datetime.utcnow() - timedelta(days=days)

    # 1) 5분봉 먼저 시도
    cursor = db.candles_5m.find(
        {"stock_code": stock_code, "datetime": {"$gte": since}},
        {"_id": 0, "datetime": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    ).sort("datetime", 1)
    docs = [doc async for doc in cursor]
    if docs:
        data = []
        for d in docs:
            dt = d["datetime"]
            dt_str = dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)
            data.append(CandleDataPoint(
                datetime=dt_str,
                open=d.get("open"), high=d.get("high"),
                low=d.get("low"), close=d.get("close"), volume=d.get("volume"),
            ))
        return CandleResponse(stock_code=stock_code, interval="5m", data=data)

    # 2) DB 일봉 데이터 확인 (daily_collect로 채워진 경우)
    cursor = db.total_trading_signals.find(
        {"stock_name": stock_code, "predicted_at": {"$gte": since}},
        {"_id": 0, "predicted_at": 1, "open": 1, "high": 1, "low": 1, "close": 1,
         "volume": 1, "ma5": 1, "ma20": 1, "ma60": 1}
    ).sort("predicted_at", 1)
    docs = [doc async for doc in cursor]

    # DB 데이터가 충분히 있으면 (날짜 수가 요청 기간의 50% 이상)
    if len(docs) >= days * 0.3:
        data = []
        for d in docs:
            dt = d["predicted_at"]
            dt_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
            data.append(CandleDataPoint(
                datetime=dt_str,
                open=d.get("open"), high=d.get("high"),
                low=d.get("low"), close=d.get("close"), volume=d.get("volume"),
                ma5=round(float(d["ma5"]), 0) if d.get("ma5") else None,
                ma20=round(float(d["ma20"]), 0) if d.get("ma20") else None,
                ma60=round(float(d["ma60"]), 0) if d.get("ma60") else None,
            ))
        return CandleResponse(stock_code=stock_code, interval="1d", data=data)

    # 3) DB 데이터 부족 → yfinance로 직접 수집
    import asyncio, functools
    import numpy as np
    import pandas as pd
    import yfinance as yf

    # 종목명으로 티커 조회
    doc_info = await db.total_trading_signals.find_one({"stock_name": stock_code}, {"stock_code": 1})
    code_str = doc_info.get("stock_code", stock_code) if doc_info else stock_code

    # 티커가 6자리 숫자면 .KS 붙이기, 아니면 종목명으로 검색 불가 → 빈 응답
    import re
    if re.match(r'^\d{6}


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
, code_str):
        ticker = code_str + ".KS"
    else:
        # stock_code가 종목명인 경우 DB에서 종목코드 찾기 어려움 → stock_code 필드로 재시도
        doc_info2 = await db.total_trading_signals.find_one({"stock_code": stock_code}, {"stock_code": 1})
        if doc_info2 and re.match(r'^\d{6}


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
, doc_info2.get("stock_code", "")):
            ticker = doc_info2["stock_code"] + ".KS"
        else:
            raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")

    buf_days = days + 70  # MA60 계산용 버퍼
    start_str = (datetime.utcnow() - timedelta(days=buf_days)).strftime("%Y-%m-%d")
    end_str = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

    def _fetch():
        raw = yf.download(ticker, start=start_str, end=end_str, interval="1d", progress=False, auto_adjust=True)
        if raw.empty:
            return []
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.droplevel(1)
        raw.columns = [c.lower() for c in raw.columns]
        raw = raw.rename(columns={"adj close": "close"})
        raw.index = pd.to_datetime(raw.index)
        raw = raw.dropna(subset=["close"])

        close = raw["close"]
        ma5  = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()

        cutoff = datetime.utcnow() - timedelta(days=days)
        result = []
        for dt, row in raw.iterrows():
            if dt.replace(tzinfo=None) < cutoff:
                continue
            def sf(v):
                try:
                    f = float(v)
                    return None if f != f else round(f, 2)
                except:
                    return None
            result.append(CandleDataPoint(
                datetime=dt.strftime("%Y-%m-%d"),
                open=sf(row.get("open")), high=sf(row.get("high")),
                low=sf(row.get("low")), close=sf(row.get("close")), volume=sf(row.get("volume")),
                ma5=sf(ma5.get(dt)), ma20=sf(ma20.get(dt)), ma60=sf(ma60.get(dt)),
            ))
        return result

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, functools.partial(_fetch))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"yfinance 수집 실패: {str(e)}")

    if not data:
        raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")

    return CandleResponse(stock_code=stock_code, interval="1d", data=data)


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
