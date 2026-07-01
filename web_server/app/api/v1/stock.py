"""
주식 관련 API
"""
import asyncio
import functools
import re
from datetime import datetime, timedelta
from typing import List, Optional

import numpy as np
import pandas as pd
import yfinance as yf
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
DEFAULT_MODEL = "ju-model-v2"


def _db() -> AsyncIOMotorDatabase:
    return get_db()


def _period_to_days(period: str) -> Optional[int]:
    if period == "all":
        return None
    return PERIOD_DAYS.get(period)


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


def _safe_float(v):
    try:
        f = float(v)
        return None if f != f else round(f, 2)
    except Exception:
        return None


def _is_code(s: str) -> bool:
    return bool(re.match(r'^\d{6}$', s))


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


@router.get("/today-signals", summary="종합 신호 목록")
async def get_today_signals(
    days: int = Query(1, ge=1, le=7, description="최근 N일 데이터 기준"),
    model_id: str = Query(DEFAULT_MODEL, description="모델 ID (ju-model-v2 / seo-model-v1)"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """
    차트 툴팁과 동일한 getCompositeSignal 로직을 전체 종목에 적용.
    오늘 날짜 기준 최신 데이터로 신호 계산 후 매수 우선 정렬 반환.
    """
    since = datetime.utcnow() - timedelta(days=days + 120)

    pipeline = [
        {"$match": {"predicted_at": {"$gte": since}, "close": {"$ne": None}, "model_id": model_id}},
        {"$sort": {"predicted_at": 1}},
        {"$group": {
            "_id": "$stock_code",
            "stock_name": {"$last": "$stock_name"},
            "closes":  {"$push": "$close"},
            "opens":   {"$push": "$open"},
            "highs":   {"$push": "$high"},
            "lows":    {"$push": "$low"},
            "ma5":     {"$last": "$ma5"},
            "ma20":    {"$last": "$ma20"},
            "ma60":    {"$last": "$ma60"},
            "ma60_prev": {"$push": "$ma60"},
        }},
    ]

    SIGNAL_ORDER = {
        "강한 매수": 0, "MA60 턴": 1, "골든보": 2, "매수 우세": 3,
        "음봉 주의": 4, "중립": 5, "매도 우세": 6, "강한 매도": 7,
        "침체(MA60)": 8, "침체(일목)": 9,
    }

    result = []
    async for doc in db.total_trading_signals.aggregate(pipeline):
        closes_raw = doc.get("closes", [])
        closes = [float(c) for c in closes_raw if c is not None]
        opens_raw = doc.get("opens", [])
        opens = [float(o) for o in opens_raw if o is not None]
        if len(closes) < 3:
            continue

        close = closes[-1]
        open_ = opens[-1] if opens else close
        ma5  = float(doc["ma5"])  if doc.get("ma5")  else (sum(closes[-5:])  / 5  if len(closes) >= 5  else None)
        ma20 = float(doc["ma20"]) if doc.get("ma20") else (sum(closes[-20:]) / 20 if len(closes) >= 20 else None)
        ma60 = float(doc["ma60"]) if doc.get("ma60") else (sum(closes[-60:]) / 60 if len(closes) >= 60 else None)

        ma60_list = [float(v) for v in doc.get("ma60_prev", []) if v is not None]
        ma60_prev  = ma60_list[-2] if len(ma60_list) >= 2 else None
        ma60_prev2 = ma60_list[-3] if len(ma60_list) >= 3 else None

        rsi_vals = _calc_rsi(closes)
        rsi = rsi_vals[-1]

        macd_line, sig_line, _ = _calc_macd(closes)
        macd     = macd_line[-1]
        macd_sig = sig_line[-1]
        macd_prev     = macd_line[-2] if len(macd_line) >= 2 else None
        macd_sig_prev = sig_line[-2]  if len(sig_line) >= 2  else None

        is_bear_candle = open_ is not None and close < open_
        ma60_falling = ma60 is not None and ma60_prev is not None and ma60 < ma60_prev
        ma60_turning = (
            ma60_prev2 is not None and ma60_prev is not None and ma60 is not None
            and ma60_prev < ma60_prev2 and ma60 >= ma60_prev
        )

        def hi(arr, n): return max(arr[-n:]) if len(arr) >= n else None
        def lo(arr, n): return min(arr[-n:]) if len(arr) >= n else None
        lows_raw = [float(v) for v in doc.get("lows", []) if v is not None]
        highs_raw = [float(v) for v in doc.get("highs", []) if v is not None]
        tenkan = ((hi(highs_raw, 9) or 0) + (lo(lows_raw, 9) or 0)) / 2 if len(highs_raw) >= 9 else None
        kijun  = ((hi(highs_raw, 26) or 0) + (lo(lows_raw, 26) or 0)) / 2 if len(highs_raw) >= 26 else None
        span_a = (tenkan + kijun) / 2 if tenkan and kijun else None
        span_b = ((hi(highs_raw, 52) or 0) + (lo(lows_raw, 52) or 0)) / 2 if len(highs_raw) >= 52 else None
        ichimoku_stagnant = (
            span_a and span_b and close
            and span_a < span_b and close < span_a
        )

        golden_bo = False
        if (ma60 and not ma60_falling and close > ma60
                and macd and macd_sig and macd > macd_sig
                and not ichimoku_stagnant):
            recent = closes[-20:]
            if any(c < ma60 * 1.01 for c in recent[:-1]):
                golden_bo = True

        if golden_bo:
            signal = "골든보"; sub = "MA60 U자 지지 반등"
        elif ichimoku_stagnant:
            signal = "침체(일목)"; sub = "선행스팬 역배열"
        elif ma60_falling:
            signal = "침체(MA60)"; sub = "MA60 하락중"
        elif ma60_turning:
            signal = "MA60 턴"; sub = "60일선 반등 전환점"
        elif rsi is not None and rsi_vals[-2] is not None and rsi_vals[-2] >= 70 and rsi < 70:
            signal = "강한 매도"; sub = "RSI 70 하방이탈"
        else:
            bull = 0; bear = 0
            if ma5 and ma20 and ma60:
                if ma5 > ma20 > ma60: bull += 1
                elif ma5 < ma20 < ma60: bear += 1
            if macd and macd_sig:
                if macd > macd_sig: bull += 1
                else: bear += 1
            if rsi is not None:
                if rsi <= 30: bull += 1
                elif rsi >= 70: bear += 1
                else: bull += 0.5
            score = bull - bear

            if is_bear_candle and score >= 1.5:
                signal = "음봉 주의"; sub = "지표 매수지만 음봉"
            elif score >= 2.5:
                signal = "강한 매수"; sub = "3개 지표 매수"
            elif score >= 1.5:
                signal = "매수 우세"; sub = "2개 지표 매수"
            elif score <= -2:
                signal = "강한 매도"; sub = "3개 지표 매도"
            elif score <= -1:
                signal = "매도 우세"; sub = "2개 지표 매도"
            else:
                signal = "중립"; sub = "지표 혼재"

        tags = []
        if ma5 and ma20 and ma60:
            if float(ma5) > float(ma20) > float(ma60):
                tags.append({"label": "MA 정배열", "color": "#16a34a"})
            elif float(ma5) < float(ma20) < float(ma60):
                tags.append({"label": "MA 역배열", "color": "#dc2626"})
        if macd is not None and macd_sig is not None:
            if macd > macd_sig:
                tags.append({"label": "MACD↑", "color": "#4ade80"})
            else:
                tags.append({"label": "MACD↓", "color": "#f87171"})
        if rsi is not None:
            if rsi <= 30:
                tags.append({"label": f"RSI {round(rsi,1)} 과매도", "color": "#4ade80"})
            elif rsi >= 70:
                tags.append({"label": f"RSI {round(rsi,1)} 과매수", "color": "#f87171"})
            else:
                tags.append({"label": f"RSI {round(rsi,1)}", "color": "#6b7280"})
        if golden_bo:
            tags.append({"label": "골든보", "color": "#f0abfc"})
        if ma60_turning:
            tags.append({"label": "MA60 턴", "color": "#f0abfc"})
        if is_bear_candle:
            tags.append({"label": "음봉", "color": "#f59e0b"})
        if ichimoku_stagnant:
            tags.append({"label": "일목침체", "color": "#6b7280"})
        elif span_a and span_b and close and close > max(float(span_a), float(span_b)):
            tags.append({"label": "일목양운↑", "color": "#4ade80"})

        result.append({
            "stock_code": doc["_id"],
            "stock_name": doc.get("stock_name", ""),
            "signal": signal,
            "sub": sub,
            "tags": tags,
            "close": round(float(close)) if close else None,
            "rsi": round(float(rsi), 1) if rsi is not None else None,
            "ma_align": "정배열" if (ma5 and ma20 and ma60 and float(ma5) > float(ma20) > float(ma60))
                        else "역배열" if (ma5 and ma20 and ma60 and float(ma5) < float(ma20) < float(ma60))
                        else "혼재",
            "macd_bull": bool(macd > macd_sig) if (macd is not None and macd_sig is not None) else None,
        })

    result.sort(key=lambda x: (SIGNAL_ORDER.get(x["signal"], 99)))
    return result


@router.get("/price/{stock_code}", summary="종목 현재가 조회")
async def get_current_price(
    stock_code: str,
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    doc = await db.total_trading_signals.find_one(
        {"stock_code": stock_code, "close": {"$ne": None}},
        sort=[("predicted_at", -1)],
    )
    if not doc:
        raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")
    return {
        "stock_code": stock_code,
        "stock_name": doc.get("stock_name", ""),
        "close": doc.get("close"),
        "predicted_at": doc.get("predicted_at"),
    }


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
    model_id: str = Query(DEFAULT_MODEL, description="모델 ID (ju-model-v2 / seo-model-v1)"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    query: dict = {"model_id": model_id}
    if signal in ("매수", "매도", "관망"):
        query["signal"] = signal
    if stock_name:
        query["stock_name"] = stock_name
        limit = 10000

    cursor = db.total_trading_signals.find(query).sort("predicted_at", -1).limit(limit)
    docs = [doc async for doc in cursor]

    if stock_name:
        deduped = docs
    else:
        seen: set = set()
        deduped = []
        for doc in docs:
            sname = doc.get("stock_name", "")
            if sname not in seen:
                seen.add(sname)
                deduped.append(doc)
    docs = deduped

    stock_names = list({doc.get("stock_name") for doc in docs if doc.get("stock_name")})
    prev_close_map: dict = {}

    if stock_names:
        pipeline = [
            {"$match": {"stock_name": {"$in": stock_names}, "close": {"$ne": None}, "model_id": model_id}},
            {"$sort": {"predicted_at": -1}},
            {"$group": {
                "_id": "$stock_name",
                "closes": {"$push": "$close"},
            }},
        ]
        async for row in db.total_trading_signals.aggregate(pipeline):
            closes = row.get("closes", [])
            prev_close_map[row["_id"]] = closes[1] if len(closes) > 1 else None

    result = []
    for doc in docs:
        signal_str = doc.get("signal", "관망")
        signal_label = {v: k for k, v in SIGNAL_MAP.items()}.get(signal_str, 2)
        current_price = doc.get("close")
        sname = doc.get("stock_name", "")
        prev_close = prev_close_map.get(sname)
        change_pct = None
        if current_price and prev_close and prev_close != 0:
            change_pct = round((current_price - prev_close) / prev_close * 100, 2)
        result.append(AIPredictionItem(
            stock_code=doc.get("stock_code", ""),
            stock_name=sname,
            current_price=current_price,
            change_pct=change_pct,
            signal=signal_str,
            signal_label=signal_label,
            confidence=doc.get("confidence"),
            predicted_at=doc.get("predicted_at"),
        ))
    return result


@router.get("/ai/today", response_model=List[AIPredictionItem], summary="오늘 AI 예측 목록")
async def get_today_predictions(
    signal: Optional[str] = Query(None, description="매수 / 매도 / 관망"),
    model_id: str = Query(DEFAULT_MODEL, description="모델 ID (ju-model-v2 / seo-model-v1)"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    query: dict = {"predicted_at": {"$gte": today_start}, "model_id": model_id}
    if signal in ("매수", "매도", "관망"):
        query["signal"] = signal

    cursor = db.total_trading_signals.find(query).sort("predicted_at", -1)
    docs = [doc async for doc in cursor]

    seen: set = set()
    deduped = []
    for doc in docs:
        sname = doc.get("stock_name", "")
        if sname not in seen:
            seen.add(sname)
            deduped.append(doc)

    stock_names = list({doc.get("stock_name") for doc in deduped if doc.get("stock_name")})
    prev_close_map: dict = {}
    if stock_names:
        pipeline = [
            {"$match": {"stock_name": {"$in": stock_names}, "close": {"$ne": None}, "model_id": model_id}},
            {"$sort": {"predicted_at": -1}},
            {"$group": {
                "_id": "$stock_name",
                "closes": {"$push": "$close"},
            }},
        ]
        async for row in db.total_trading_signals.aggregate(pipeline):
            closes = row.get("closes", [])
            prev_close_map[row["_id"]] = closes[1] if len(closes) > 1 else None

    result = []
    for doc in deduped:
        signal_str = doc.get("signal", "관망")
        signal_label = {v: k for k, v in SIGNAL_MAP.items()}.get(signal_str, 2)
        current_price = doc.get("close")
        sname = doc.get("stock_name", "")
        prev_close = prev_close_map.get(sname)
        change_pct = None
        if current_price and prev_close and prev_close != 0:
            change_pct = round((current_price - prev_close) / prev_close * 100, 2)
        result.append(AIPredictionItem(
            stock_code=doc.get("stock_code", ""),
            stock_name=sname,
            current_price=current_price,
            change_pct=change_pct,
            signal=signal_str,
            signal_label=signal_label,
            confidence=doc.get("confidence"),
            predicted_at=doc.get("predicted_at"),
        ))
    return result


@router.get("/ai/detail/{stock_code}", response_model=AIDetailResponse, summary="AI 분석 상세")
async def get_ai_detail(
    stock_code: str,
    model_id: str = Query(DEFAULT_MODEL, description="모델 ID"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    doc = await db.total_trading_signals.find_one(
        {"stock_code": stock_code, "model_id": model_id},
        sort=[("predicted_at", -1)]
    )
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
    stock_code: str,
    period: str = Query("3m", description="1m / 3m / 6m / all"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    days = _period_to_days(period)
    if days is None and period != "all":
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나여야 합니다.")

    query: dict = {"stock_code": stock_code}
    if days is not None:
        query["predicted_at"] = {"$gte": datetime.utcnow() - timedelta(days=days + 20)}

    cursor = db.total_trading_signals.find(
        query,
        {"predicted_at": 1, "close": 1, "rsi": 1, "stock_name": 1, "_id": 0}
    ).sort("predicted_at", 1)
    docs = [doc async for doc in cursor]
    if not docs:
        raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name", "")
    cutoff = datetime.utcnow() - timedelta(days=days) if days is not None else None

    data = []
    has_rsi = any(d.get("rsi") is not None for d in docs)
    if has_rsi:
        for d in docs:
            dt = d["predicted_at"]
            dt_naive = dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt
            if (cutoff is None or dt_naive >= cutoff) and d.get("rsi") is not None:
                data.append(RSIDataPoint(date=dt.strftime("%Y-%m-%d"), rsi=round(float(d["rsi"]), 2)))
    else:
        closes = [float(d["close"]) for d in docs if d.get("close")]
        dates = [d["predicted_at"] for d in docs if d.get("close")]
        rsi_values = _calc_rsi(closes)
        for i, dt in enumerate(dates):
            dt_naive = dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt
            if (cutoff is None or dt_naive >= cutoff) and rsi_values[i] is not None:
                data.append(RSIDataPoint(date=dt.strftime("%Y-%m-%d"), rsi=round(rsi_values[i], 2)))

    return RSIResponse(stock_code=stock_code, stock_name=stock_name, period=period, data=data)


@router.get("/chart/macd/{stock_code}", response_model=MACDResponse, summary="MACD 차트 데이터")
async def get_macd(
    stock_code: str,
    period: str = Query("3m", description="1m / 3m / 6m / all"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    days = _period_to_days(period)
    if days is None and period != "all":
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나여야 합니다.")

    query: dict = {"stock_code": stock_code}
    if days is not None:
        query["predicted_at"] = {"$gte": datetime.utcnow() - timedelta(days=days + 40)}

    cursor = db.total_trading_signals.find(
        query,
        {"predicted_at": 1, "close": 1, "macd": 1, "stock_name": 1, "_id": 0}
    ).sort("predicted_at", 1)
    docs = [doc async for doc in cursor]
    if not docs:
        raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name", "")
    cutoff = datetime.utcnow() - timedelta(days=days) if days is not None else None

    closes = [float(d["close"]) for d in docs if d.get("close")]
    dates = [d["predicted_at"] for d in docs if d.get("close")]
    macd_line, signal_line, histogram = _calc_macd(closes)

    data = []
    for i, dt in enumerate(dates):
        dt_naive = dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt
        if (cutoff is None or dt_naive >= cutoff) and macd_line[i] is not None:
            data.append(MACDDataPoint(
                date=dt.strftime("%Y-%m-%d"),
                macd=round(macd_line[i], 4),
                signal=round(signal_line[i], 4),
                histogram=round(histogram[i], 4),
            ))
    return MACDResponse(stock_code=stock_code, stock_name=stock_name, period=period, data=data)


def _fetch_candle_from_yfinance(ticker_code: str, fetch_days: int = 365) -> List[CandleDataPoint]:
    """yfinance에서 캔들 데이터 수집 후 반환."""
    ticker = ticker_code + ".KS"
    start_str = (datetime.utcnow() - timedelta(days=fetch_days + 70)).strftime("%Y-%m-%d")
    end_str = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

    raw = yf.download(ticker, start=start_str, end=end_str, interval="1d", progress=False, auto_adjust=True)
    if raw.empty:
        return []
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [c.lower() for c in raw.columns]
    raw = raw.rename(columns={"adj close": "close"})
    raw.index = pd.to_datetime(raw.index)
    raw = raw.dropna(subset=["close"])
    close_s = raw["close"]
    ma5 = close_s.rolling(5).mean()
    ma20 = close_s.rolling(20).mean()
    ma60 = close_s.rolling(60).mean()
    result = []
    for dt, row in raw.iterrows():
        result.append(CandleDataPoint(
            datetime=dt.strftime("%Y-%m-%d"),
            open=_safe_float(row.get("open")),
            high=_safe_float(row.get("high")),
            low=_safe_float(row.get("low")),
            close=_safe_float(row.get("close")),
            volume=_safe_float(row.get("volume")),
            ma5=_safe_float(ma5.get(dt)),
            ma20=_safe_float(ma20.get(dt)),
            ma60=_safe_float(ma60.get(dt)),
        ))
    return result


@router.get("/chart/candle/{stock_code}", response_model=CandleResponse, summary="캔들 차트 데이터")
async def get_candles(
    stock_code: str,
    days: int = Query(0, ge=0, le=9999, description="0이면 전체 기간"),
    model_id: str = Query(DEFAULT_MODEL, description="모델 ID (ju-model-v2 / seo-model-v1)"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    query: dict = {"$or": [{"stock_code": stock_code}, {"stock_name": stock_code}], "model_id": model_id}
    if days > 0:
        query["predicted_at"] = {"$gte": datetime.utcnow() - timedelta(days=days)}

    cursor = db.total_trading_signals.find(
        query,
        {"_id": 0, "predicted_at": 1, "open": 1, "high": 1, "low": 1, "close": 1,
         "volume": 1, "ma5": 1, "ma20": 1, "ma60": 1}
    ).sort("predicted_at", 1)
    docs = [doc async for doc in cursor]

    # DB 데이터가 있고 최신 날짜가 3일 이내면 DB 데이터 반환
    if docs:
        last_dt = docs[-1]["predicted_at"]
        last_dt_naive = last_dt.replace(tzinfo=None) if hasattr(last_dt, "replace") else last_dt
        is_stale = (datetime.utcnow() - last_dt_naive).days >= 3

        if not is_stale:
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

        # 오래된 데이터 -> 종목코드 확보 후 yfinance 폴백
        if not _is_code(stock_code):
            doc_info2 = await db.total_trading_signals.find_one(
                {"stock_name": stock_code}, {"stock_code": 1}
            )
            if doc_info2:
                stock_code = doc_info2.get("stock_code", stock_code)

    # DB 데이터 없거나 오래됐으면 yfinance 직접 수집
    if not _is_code(stock_code):
        doc_info = await db.total_trading_signals.find_one(
            {"stock_name": stock_code}, {"stock_code": 1}
        )
        ticker_code = doc_info.get("stock_code", "") if doc_info else ""
        if not _is_code(ticker_code):
            raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")
    else:
        ticker_code = stock_code

    fetch_days = days if days > 0 else 365

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, functools.partial(_fetch_candle_from_yfinance, ticker_code, fetch_days)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"yfinance 수집 실패: {str(e)}")

    if not data:
        raise HTTPException(status_code=404, detail="해당 종목 데이터가 없습니다.")

    return CandleResponse(stock_code=stock_code, interval="1d", data=data)


@router.get("/chart/candle5m/{stock_code}", response_model=CandleResponse, summary="5분봉 차트 데이터")
async def get_candles_5m(
    stock_code: str,
    days: int = Query(1, ge=1, le=90),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    from datetime import timezone as tz
    since = datetime.utcnow() - timedelta(days=days)
    cursor = db.candles_5m.find(
        {"stock_code": stock_code, "datetime": {"$gte": since}},
        {"_id": 0, "datetime": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    ).sort("datetime", 1)
    docs = [doc async for doc in cursor]
    if not docs:
        raise HTTPException(status_code=404, detail="5분봉 데이터가 없습니다.")

    data = []
    for d in docs:
        dt = d["datetime"]
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz.utc)
        kst = dt + timedelta(hours=9)
        dt_str = kst.strftime("%Y-%m-%d %H:%M")
        data.append(CandleDataPoint(
            datetime=dt_str,
            open=_safe_float(d.get("open")),
            high=_safe_float(d.get("high")),
            low=_safe_float(d.get("low")),
            close=_safe_float(d.get("close")),
            volume=_safe_float(d.get("volume")),
        ))
    return CandleResponse(stock_code=stock_code, interval="5m", data=data)
