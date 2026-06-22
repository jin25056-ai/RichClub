"""
글로벌 시장 현황 + 승률 테스트 API
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, Query, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.db.mongo import get_db

router = APIRouter(prefix="/market", tags=["market"])


def _db() -> AsyncIOMotorDatabase:
    return get_db()


# ── 스키마 ─────────────────────────────────────────────────────────────────────

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


class WinRateResult(BaseModel):
    signal: str
    total_signals: int
    win_count: int
    lose_count: int
    win_rate: float
    avg_return_pct: float
    max_return_pct: float
    max_loss_pct: float
    hold_days: int


class WinRateResponse(BaseModel):
    stock_code: Optional[str]
    stock_name: Optional[str]
    period: str
    results: List[WinRateResult]
    updated_at: datetime


# ── 글로벌 시장 현황 ───────────────────────────────────────────────────────────

GLOBAL_SYMBOLS = [
    {"symbol": "^IXIC",    "name": "나스닥"},
    {"symbol": "^GSPC",    "name": "S&P500"},
    {"symbol": "^SOX",     "name": "필라델피아 반도체"},
    {"symbol": "QQQ",      "name": "나스닥100 ETF"},
    {"symbol": "USDKRW=X", "name": "달러/원 환율"},
    {"symbol": "CL=F",     "name": "WTI 원유"},
    {"symbol": "^VIX",     "name": "VIX 공포지수"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


async def _fetch_symbol(client: httpx.AsyncClient, symbol: str) -> dict:
    """Yahoo Finance v8 API로 단일 심볼 조회"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "2d"}
    try:
        res = await client.get(url, params=params, headers=HEADERS, timeout=10)
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
    if change_pct >= 0.3:
        return "up"
    if change_pct <= -0.3:
        return "down"
    return "flat"


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

    if score >= 2:
        signal = "매수 우호"
    elif score <= -2:
        signal = "매수 비우호"
    else:
        signal = "중립"

    reason = " / ".join(reasons) if reasons else "뚜렷한 시장 신호 없음"
    return signal, reason


@router.get("/global", response_model=GlobalMarketResponse, summary="글로벌 시장 현황")
async def get_global_market(
    _: dict = Depends(get_current_user),
):
    async with httpx.AsyncClient() as client:
        tasks = [_fetch_symbol(client, s["symbol"]) for s in GLOBAL_SYMBOLS]
        results = await asyncio.gather(*tasks)

    items = []
    for info, result in zip(GLOBAL_SYMBOLS, results):
        change_pct = result.get("change_pct")
        items.append(GlobalMarketItem(
            symbol=info["symbol"],
            name=info["name"],
            price=result.get("price"),
            change_pct=change_pct,
            trend=_get_trend(change_pct),
        ))

    invest_signal, invest_reason = _calc_invest_signal(items)

    return GlobalMarketResponse(
        updated_at=datetime.now(timezone.utc),
        items=items,
        invest_signal=invest_signal,
        invest_reason=invest_reason,
    )


# ── 승률 테스트 ────────────────────────────────────────────────────────────────

PERIOD_DAYS_MAP = {"1m": 30, "3m": 90, "6m": 180, "all": 99999}


@router.get("/winrate", response_model=WinRateResponse, summary="승률 테스트")
async def get_win_rate(
    stock_code: Optional[str] = Query(None, description="종목코드 (없으면 전체)"),
    period: str = Query("3m", description="기간: 1m / 3m / 6m / all"),
    hold_days: int = Query(5, ge=1, le=30, description="보유 일수 기준"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    days = PERIOD_DAYS_MAP[period]
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query: dict = {"predicted_at": {"$gte": since}}
    if stock_code:
        query["stock_code"] = stock_code

    cursor = db.total_trading_signals.find(query).sort("predicted_at", 1)
    docs = [doc async for doc in cursor]

    if not docs:
        raise HTTPException(status_code=404, detail="해당 기간의 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name") if docs else None

    from collections import defaultdict
    price_map = defaultdict(list)
    for doc in docs:
        sc = doc.get("stock_code", "")
        dt = doc.get("predicted_at")
        close = doc.get("close")
        if sc and dt and close:
            price_map[sc].append((dt, float(close)))

    signal_returns = {"매수": [], "매도": [], "관망": []}

    for doc in docs:
        sc = doc.get("stock_code", "")
        signal = doc.get("signal", "관망")
        dt = doc.get("predicted_at")
        close = doc.get("close")

        if not (sc and dt and close and signal in signal_returns):
            continue

        prices = price_map[sc]
        future_prices = [
            p_close for p_dt, p_close in prices
            if timedelta(days=hold_days - 1) <= (p_dt - dt) <= timedelta(days=hold_days + 2)
        ]

        if future_prices:
            ret_pct = (future_prices[0] - float(close)) / float(close) * 100
            signal_returns[signal].append(round(ret_pct, 2))

    results = []
    for signal, returns in signal_returns.items():
        if not returns:
            continue
        win = [r for r in returns if r > 0]
        lose = [r for r in returns if r <= 0]
        results.append(WinRateResult(
            signal=signal,
            total_signals=len(returns),
            win_count=len(win),
            lose_count=len(lose),
            win_rate=round(len(win) / len(returns) * 100, 1),
            avg_return_pct=round(sum(returns) / len(returns), 2),
            max_return_pct=round(max(returns), 2),
            max_loss_pct=round(min(returns), 2),
            hold_days=hold_days,
        ))

    return WinRateResponse(
        stock_code=stock_code,
        stock_name=stock_name,
        period=period,
        results=results,
        updated_at=datetime.now(timezone.utc),
    )
