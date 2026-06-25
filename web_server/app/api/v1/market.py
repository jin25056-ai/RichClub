"""
글로벌 시장 현황 + 승률 테스트 API
- Yahoo Finance 429 방지: 서버 메모리 캐시 10분
- MA60 하락 구간: 매수 금지 (침체 구간)
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from collections import defaultdict

import httpx
from fastapi import APIRouter, Depends, Query, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.db.mongo import get_db

router = APIRouter(prefix="/market", tags=["market"])


def _db() -> AsyncIOMotorDatabase:
    return get_db()


# 스키마
class GlobalMarketItem(BaseModel):
    symbol: str
    name: str
    price: Optional[float]
    change_pct: Optional[float]
    trend: str


class GlobalMarketResponse(BaseModel):
    updated_at: datetime
    items: List[GlobalMarketItem]
    invest_signal: str
    invest_reason: str


class TradeRecord(BaseModel):
    buy_date: str
    buy_price: float
    sell_date: Optional[str] = None
    sell_price: Optional[float] = None
    return_pct: Optional[float] = None
    unrealized_pct: Optional[float] = None


class WinRateResult(BaseModel):
    signal: str
    total_signals: int
    win_count: int
    lose_count: int
    win_rate: float
    avg_return_pct: float
    max_return_pct: float
    max_loss_pct: float
    cumulative_return_pct: float
    unrealized_pct: Optional[float] = None
    hold_days: int


class WinRateResponse(BaseModel):
    stock_code: Optional[str]
    stock_name: Optional[str]
    period: str
    results: List[WinRateResult]
    trades: List[TradeRecord]
    updated_at: datetime


# 캐시 (10분)
_cache: dict = {"data": None, "ts": 0}
CACHE_TTL = 600

GLOBAL_SYMBOLS = [
    {"symbol": "^IXIC",    "name": "나스닥"},
    {"symbol": "^GSPC",    "name": "S&P500"},
    {"symbol": "^SOX",     "name": "필라델피아 반도체"},
    {"symbol": "QQQ",      "name": "나스닥100 ETF"},
    {"symbol": "USDKRW=X", "name": "달러/원 환율"},
    {"symbol": "CL=F",     "name": "WTI 원유"},
    {"symbol": "GC=F",     "name": "금"},
    {"symbol": "^VIX",     "name": "VIX 공포지수"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com",
}


async def _fetch_symbol(client: httpx.AsyncClient, symbol: str) -> dict:
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "5d"}
    try:
        res = await client.get(url, params=params, headers=HEADERS, timeout=15)
        if res.status_code == 429:
            url2 = url.replace("query2", "query1")
            res = await client.get(url2, params=params, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return {"price": None, "change_pct": None}
        data = res.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) >= 2:
            price = closes[-1]
            prev = closes[-2]
            change_pct = round((price - prev) / prev * 100, 2)
        elif len(closes) == 1:
            price = closes[-1]
            change_pct = None
        else:
            return {"price": None, "change_pct": None}
        return {"price": round(price, 2), "change_pct": change_pct}
    except Exception:
        return {"price": None, "change_pct": None}


def _get_trend(change_pct: Optional[float]) -> str:
    if change_pct is None:
        return "flat"
    return "up" if change_pct >= 0.3 else "down" if change_pct <= -0.3 else "flat"


def _calc_invest_signal(items: List[GlobalMarketItem]) -> tuple:
    score = 0
    reasons = []
    item_map = {i.symbol: i for i in items}

    nasdaq = item_map.get("^IXIC")
    if nasdaq and nasdaq.change_pct is not None:
        if nasdaq.change_pct >= 1.0:
            score += 2
            reasons.append(f"나스닥 +{nasdaq.change_pct:.1f}% 상승")
        elif nasdaq.change_pct <= -1.0:
            score -= 2
            reasons.append(f"나스닥 {nasdaq.change_pct:.1f}% 하락")

    vix = item_map.get("^VIX")
    if vix and vix.price is not None:
        if vix.price < 15:
            score += 1
            reasons.append(f"VIX {vix.price:.1f} (시장 안정)")
        elif vix.price > 25:
            score -= 2
            reasons.append(f"VIX {vix.price:.1f} (공포 구간)")

    usd = item_map.get("USDKRW=X")
    if usd and usd.change_pct is not None:
        if usd.change_pct >= 1.0:
            score -= 1
            reasons.append(f"달러/원 {usd.change_pct:.1f}% 상승 (원화 약세)")
        elif usd.change_pct <= -0.5:
            score += 1
            reasons.append(f"달러/원 {usd.change_pct:.1f}% 하락 (원화 강세)")

    wti = item_map.get("CL=F")
    if wti and wti.change_pct is not None:
        if wti.change_pct >= 3.0:
            score -= 1
            reasons.append(f"WTI 원유 {wti.change_pct:.1f}% 급등")

    sp500 = item_map.get("^GSPC")
    if sp500 and sp500.change_pct is not None:
        if sp500.change_pct >= 1.0:
            score += 1
            reasons.append(f"S&P500 +{sp500.change_pct:.1f}% 상승")
        elif sp500.change_pct <= -1.0:
            score -= 1
            reasons.append(f"S&P500 {sp500.change_pct:.1f}% 하락")

    sox = item_map.get("^SOX")
    if sox and sox.change_pct is not None:
        if sox.change_pct >= 2.0:
            score += 1
            reasons.append(f"필라델피아 반도체 +{sox.change_pct:.1f}% 상승")
        elif sox.change_pct <= -2.0:
            score -= 1
            reasons.append(f"필라델피아 반도체 {sox.change_pct:.1f}% 하락")

    gold = item_map.get("GC=F")
    if gold and gold.change_pct is not None:
        if gold.change_pct >= 1.0:
            score -= 1
            reasons.append(f"금 +{gold.change_pct:.1f}% 급등 (위험회피)")

    if score >= 2:
        signal = "매수 우호"
    elif score <= -2:
        signal = "매수 비우호"
    else:
        signal = "중립"

    reason = " / ".join(reasons) if reasons else "뚜렷한 시장 신호 없음"
    return signal, reason


async def _fetch_all_symbols() -> GlobalMarketResponse:
    items = []
    async with httpx.AsyncClient() as client:
        for info in GLOBAL_SYMBOLS:
            result = await _fetch_symbol(client, info["symbol"])
            change_pct = result.get("change_pct")
            items.append(GlobalMarketItem(
                symbol=info["symbol"],
                name=info["name"],
                price=result.get("price"),
                change_pct=change_pct,
                trend=_get_trend(change_pct),
            ))
            await asyncio.sleep(0.5)

    invest_signal, invest_reason = _calc_invest_signal(items)
    return GlobalMarketResponse(
        updated_at=datetime.now(timezone.utc),
        items=items,
        invest_signal=invest_signal,
        invest_reason=invest_reason,
    )


@router.get("/global", response_model=GlobalMarketResponse, summary="글로벌 시장 현황")
async def get_global_market(_: dict = Depends(get_current_user)):
    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]
    data = await _fetch_all_symbols()
    _cache["data"] = data
    _cache["ts"] = now
    return data


# 승률 테스트
PERIOD_DAYS_MAP = {"1m": 30, "3m": 90, "6m": 180, "all": 99999}


def _parse_date_input(s: str) -> datetime:
    """YYMMDD 또는 YYYY-MM-DD 형식을 파싱"""
    s = s.strip()
    if len(s) == 6 and s.isdigit():
        s = f"20{s[:2]}-{s[2:4]}-{s[4:6]}"
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _to_date(dt) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if hasattr(dt, 'replace'):
        return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    return dt


def _ma60_falling(ma60, prev_ma60) -> bool:
    """MA60 하락 중 여부 - 침체 구간 판단"""
    if ma60 is None or prev_ma60 is None:
        return False
    return float(ma60) < float(prev_ma60)


def _build_winrate_response(
    stock_code, stock_name, period, hold_days,
    realized_returns, unrealized_positions, trades, signal_label
):
    results = []
    if realized_returns:
        win = [r for r in realized_returns if r > 0]
        lose = [r for r in realized_returns if r <= 0]
        cumulative = 1.0
        for r in realized_returns:
            cumulative *= (1 + r / 100)
        cumulative_pct = round((cumulative - 1) * 100, 2)
        avg_unrealized = round(sum(unrealized_positions) / len(unrealized_positions), 2) if unrealized_positions else None
        results.append(WinRateResult(
            signal=signal_label,
            total_signals=len(realized_returns),
            win_count=len(win),
            lose_count=len(lose),
            win_rate=round(len(win) / len(realized_returns) * 100, 1),
            avg_return_pct=round(sum(realized_returns) / len(realized_returns), 2),
            max_return_pct=round(max(realized_returns), 2),
            max_loss_pct=round(min(realized_returns), 2),
            cumulative_return_pct=cumulative_pct,
            unrealized_pct=avg_unrealized,
            hold_days=hold_days,
        ))
    elif unrealized_positions:
        avg_unrealized = round(sum(unrealized_positions) / len(unrealized_positions), 2)
        results.append(WinRateResult(
            signal=signal_label + "(보유중)",
            total_signals=0, win_count=0, lose_count=0, win_rate=0,
            avg_return_pct=0, max_return_pct=0, max_loss_pct=0,
            cumulative_return_pct=0, unrealized_pct=avg_unrealized, hold_days=hold_days,
        ))
    return WinRateResponse(
        stock_code=stock_code, stock_name=stock_name, period=period,
        results=results, trades=trades, updated_at=datetime.now(timezone.utc),
    )


@router.get("/winrate", response_model=WinRateResponse, summary="승률 테스트 (AI) - MA60 하락 구간 매수 제외")
async def get_win_rate(
    stock_code: Optional[str] = Query(None),
    period: str = Query("3m"),
    hold_days: int = Query(5, ge=1, le=30),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """
    AI 승률 테스트
    - 매수: AI 매수 신호 + MA60 하락 구간 제외
    - 매도: AI 매도 신호
    """
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    since = _parse_date_input(start_date) if start_date else datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS_MAP[period])
    until = (_parse_date_input(end_date) + timedelta(days=1)) if end_date else datetime.now(timezone.utc) + timedelta(days=1)

    query: dict = {"predicted_at": {"$gte": since, "$lt": until}}
    if stock_code:
        query["$or"] = [{"stock_code": stock_code}, {"stock_name": stock_code}]

    docs = [doc async for doc in db.total_trading_signals.find(query).sort("predicted_at", 1)]
    if not docs:
        raise HTTPException(status_code=404, detail="해당 기간의 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name") if docs else None
    sc_docs: dict = defaultdict(list)
    for doc in docs:
        sc = doc.get("stock_code", "")
        if sc:
            sc_docs[sc].append(doc)

    trades: list = []
    realized_returns: list = []
    unrealized_positions: list = []

    for sc, sdocs in sc_docs.items():
        position = None
        latest_price = None
        prev_ma60 = None

        for doc in sdocs:
            signal = doc.get("signal", "관망")
            dt = _to_date(doc.get("predicted_at"))
            close = doc.get("close")
            ma60 = doc.get("ma60")
            if close is None:
                continue
            close = float(close)
            latest_price = close
            date_str = dt.strftime("%Y-%m-%d")

            # MA60 하락 구간은 매수 금지
            if signal == "매수" and position is None and not _ma60_falling(ma60, prev_ma60):
                position = {"buy_date": date_str, "buy_price": close}
            elif signal == "매도" and position is not None:
                ret_pct = round((close - position["buy_price"]) / position["buy_price"] * 100, 2)
                trades.append(TradeRecord(
                    buy_date=position["buy_date"], buy_price=position["buy_price"],
                    sell_date=date_str, sell_price=close, return_pct=ret_pct,
                ))
                realized_returns.append(ret_pct)
                position = None

            if ma60 is not None:
                prev_ma60 = float(ma60)

        if position is not None and latest_price is not None:
            unrealized_pct = round((latest_price - position["buy_price"]) / position["buy_price"] * 100, 2)
            unrealized_positions.append(unrealized_pct)
            trades.append(TradeRecord(
                buy_date=position["buy_date"], buy_price=position["buy_price"],
                sell_date=None, sell_price=latest_price, unrealized_pct=unrealized_pct,
            ))

    return _build_winrate_response(stock_code, stock_name, period, hold_days,
                                   realized_returns, unrealized_positions, trades,
                                   "매수(AI+MA60상승)→매도(AI)")


@router.get("/winrate/simple", response_model=WinRateResponse, summary="승률 테스트 (AI 매수 + 5일선 매도) - MA60 하락 제외")
async def get_win_rate_simple(
    stock_code: Optional[str] = Query(None),
    period: str = Query("3m"),
    hold_days: int = Query(5, ge=1, le=30),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """
    단순 승률 테스트
    - 매수: AI 매수 신호 + MA60 하락 구간 제외
    - 매도: 5일선 꺾임(ma5 < 전날 ma5)
    """
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    since = _parse_date_input(start_date) if start_date else datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS_MAP[period])
    until = (_parse_date_input(end_date) + timedelta(days=1)) if end_date else datetime.now(timezone.utc) + timedelta(days=1)

    query: dict = {"predicted_at": {"$gte": since, "$lt": until}}
    if stock_code:
        query["$or"] = [{"stock_code": stock_code}, {"stock_name": stock_code}]

    docs = [doc async for doc in db.total_trading_signals.find(query).sort("predicted_at", 1)]
    if not docs:
        raise HTTPException(status_code=404, detail="해당 기간의 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name") if docs else None
    sc_docs: dict = defaultdict(list)
    for doc in docs:
        sc = doc.get("stock_code", "")
        if sc:
            sc_docs[sc].append(doc)

    trades: list = []
    realized_returns: list = []
    unrealized_positions: list = []

    for sc, sdocs in sc_docs.items():
        position = None
        latest_price = None
        prev_ma5 = None
        prev_ma60 = None

        for doc in sdocs:
            signal = doc.get("signal", "관망")
            dt = _to_date(doc.get("predicted_at"))
            close = doc.get("close")
            ma5 = doc.get("ma5")
            ma60 = doc.get("ma60")
            if close is None:
                continue
            close = float(close)
            latest_price = close
            date_str = dt.strftime("%Y-%m-%d")

            ma5_turning_down = (ma5 is not None and prev_ma5 is not None
                                and float(ma5) < float(prev_ma5))

            # MA60 하락 구간은 매수 금지
            if signal == "매수" and position is None and not _ma60_falling(ma60, prev_ma60):
                position = {"buy_date": date_str, "buy_price": close}
            elif ma5_turning_down and position is not None:
                ret_pct = round((close - position["buy_price"]) / position["buy_price"] * 100, 2)
                trades.append(TradeRecord(
                    buy_date=position["buy_date"], buy_price=position["buy_price"],
                    sell_date=date_str, sell_price=close, return_pct=ret_pct,
                ))
                realized_returns.append(ret_pct)
                position = None

            if ma5 is not None:
                prev_ma5 = float(ma5)
            if ma60 is not None:
                prev_ma60 = float(ma60)

        if position is not None and latest_price is not None:
            unrealized_pct = round((latest_price - position["buy_price"]) / position["buy_price"] * 100, 2)
            unrealized_positions.append(unrealized_pct)
            trades.append(TradeRecord(
                buy_date=position["buy_date"], buy_price=position["buy_price"],
                sell_date=None, sell_price=latest_price, unrealized_pct=unrealized_pct,
            ))

    return _build_winrate_response(stock_code, stock_name, period, hold_days,
                                   realized_returns, unrealized_positions, trades,
                                   "매수(AI+MA60상승)→매도(5일선꺾임)")


@router.get("/winrate/combined", response_model=WinRateResponse, summary="승률 테스트 (AI+정배열 매수) - MA60 하락 제외")
async def get_win_rate_combined(
    stock_code: Optional[str] = Query(None),
    period: str = Query("3m"),
    hold_days: int = Query(5, ge=1, le=30),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """
    AI+지표 동시 매수 승률 테스트
    - 매수: AI 매수 신호 + MA 정배열(ma5>ma20>ma60) + MA60 상승 중
    - 매도: AI 매도 신호 or MA 역배열(ma5<ma20<ma60)
    """
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    since = _parse_date_input(start_date) if start_date else datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS_MAP[period])
    until = (_parse_date_input(end_date) + timedelta(days=1)) if end_date else datetime.now(timezone.utc) + timedelta(days=1)

    query: dict = {"predicted_at": {"$gte": since, "$lt": until}}
    if stock_code:
        query["$or"] = [{"stock_code": stock_code}, {"stock_name": stock_code}]

    docs = [doc async for doc in db.total_trading_signals.find(query).sort("predicted_at", 1)]
    if not docs:
        raise HTTPException(status_code=404, detail="해당 기간의 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name") if docs else None
    sc_docs: dict = defaultdict(list)
    for doc in docs:
        sc = doc.get("stock_code", "")
        if sc:
            sc_docs[sc].append(doc)

    trades: list = []
    realized_returns: list = []
    unrealized_positions: list = []

    for sc, sdocs in sc_docs.items():
        position = None
        latest_price = None
        prev_ma60 = None

        for doc in sdocs:
            signal = doc.get("signal", "관망")
            dt = _to_date(doc.get("predicted_at"))
            close = doc.get("close")
            ma5 = doc.get("ma5")
            ma20 = doc.get("ma20")
            ma60 = doc.get("ma60")
            if close is None:
                continue
            close = float(close)
            latest_price = close
            date_str = dt.strftime("%Y-%m-%d")

            ma_bullish = (ma5 is not None and ma20 is not None and ma60 is not None
                          and float(ma5) > float(ma20) > float(ma60))
            ma_bearish = (ma5 is not None and ma20 is not None and ma60 is not None
                          and float(ma5) < float(ma20) < float(ma60))

            # MA60 하락 구간은 매수 금지
            if signal == "매수" and ma_bullish and position is None and not _ma60_falling(ma60, prev_ma60):
                position = {"buy_date": date_str, "buy_price": close}
            elif position is not None and (signal == "매도" or ma_bearish):
                ret_pct = round((close - position["buy_price"]) / position["buy_price"] * 100, 2)
                trades.append(TradeRecord(
                    buy_date=position["buy_date"], buy_price=position["buy_price"],
                    sell_date=date_str, sell_price=close, return_pct=ret_pct,
                ))
                realized_returns.append(ret_pct)
                position = None

            if ma60 is not None:
                prev_ma60 = float(ma60)

        if position is not None and latest_price is not None:
            unrealized_pct = round((latest_price - position["buy_price"]) / position["buy_price"] * 100, 2)
            unrealized_positions.append(unrealized_pct)
            trades.append(TradeRecord(
                buy_date=position["buy_date"], buy_price=position["buy_price"],
                sell_date=None, sell_price=latest_price, unrealized_pct=unrealized_pct,
            ))

    return _build_winrate_response(stock_code, stock_name, period, hold_days,
                                   realized_returns, unrealized_positions, trades,
                                   "매수(AI+정배열+MA60상승)→매도(AI or 역배열)")


@router.get("/winrate/indicator", response_model=WinRateResponse, summary="승률 테스트 (지표만) - MA60 하락 제외")
async def get_win_rate_indicator(
    stock_code: Optional[str] = Query(None),
    period: str = Query("3m"),
    hold_days: int = Query(5, ge=1, le=30),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """
    지표만 승률 테스트 (AI 신호 무시)
    - 매수: MA 정배열 첫 진입 + MA60 상승 중
    - 매도: MA 역배열 전환
    """
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    since = _parse_date_input(start_date) if start_date else datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS_MAP[period])
    until = (_parse_date_input(end_date) + timedelta(days=1)) if end_date else datetime.now(timezone.utc) + timedelta(days=1)

    query: dict = {"predicted_at": {"$gte": since, "$lt": until}}
    if stock_code:
        query["$or"] = [{"stock_code": stock_code}, {"stock_name": stock_code}]

    docs = [doc async for doc in db.total_trading_signals.find(query).sort("predicted_at", 1)]
    if not docs:
        raise HTTPException(status_code=404, detail="해당 기간의 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name") if docs else None
    sc_docs: dict = defaultdict(list)
    for doc in docs:
        sc = doc.get("stock_code", "")
        if sc:
            sc_docs[sc].append(doc)

    trades: list = []
    realized_returns: list = []
    unrealized_positions: list = []

    for sc, sdocs in sc_docs.items():
        position = None
        latest_price = None
        prev_in_bullish = False
        prev_ma60 = None

        for doc in sdocs:
            dt = _to_date(doc.get("predicted_at"))
            close = doc.get("close")
            ma5 = doc.get("ma5")
            ma20 = doc.get("ma20")
            ma60 = doc.get("ma60")
            if close is None:
                continue
            close = float(close)
            latest_price = close
            date_str = dt.strftime("%Y-%m-%d")

            ma_bullish = (ma5 is not None and ma20 is not None and ma60 is not None
                          and float(ma5) > float(ma20) > float(ma60))
            ma_bearish = (ma5 is not None and ma20 is not None and ma60 is not None
                          and float(ma5) < float(ma20) < float(ma60))

            # MA60 하락 구간은 매수 금지
            if ma_bullish and not prev_in_bullish and position is None and not _ma60_falling(ma60, prev_ma60):
                position = {"buy_date": date_str, "buy_price": close}
            elif ma_bearish and position is not None:
                ret_pct = round((close - position["buy_price"]) / position["buy_price"] * 100, 2)
                trades.append(TradeRecord(
                    buy_date=position["buy_date"], buy_price=position["buy_price"],
                    sell_date=date_str, sell_price=close, return_pct=ret_pct,
                ))
                realized_returns.append(ret_pct)
                position = None

            prev_in_bullish = ma_bullish
            if ma60 is not None:
                prev_ma60 = float(ma60)

        if position is not None and latest_price is not None:
            unrealized_pct = round((latest_price - position["buy_price"]) / position["buy_price"] * 100, 2)
            unrealized_positions.append(unrealized_pct)
            trades.append(TradeRecord(
                buy_date=position["buy_date"], buy_price=position["buy_price"],
                sell_date=None, sell_price=latest_price, unrealized_pct=unrealized_pct,
            ))

    return _build_winrate_response(stock_code, stock_name, period, hold_days,
                                   realized_returns, unrealized_positions, trades,
                                   "매수(MA정배열+MA60상승)→매도(MA역배열)")
