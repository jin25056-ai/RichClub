"""
글로벌 시장 현황 + 승률 테스트 API
- Yahoo Finance 429 방지: 서버 메모리 캐시 10분
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
    return_pct: Optional[float] = None  # 청산된 경우
    unrealized_pct: Optional[float] = None  # 미청산인 경우


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
    unrealized_pct: Optional[float] = None   # 현재 보유 중인 미실현 손익
    hold_days: int


class WinRateResponse(BaseModel):
    stock_code: Optional[str]
    stock_name: Optional[str]
    period: str
    results: List[WinRateResult]
    trades: List[TradeRecord]   # 실제 거래 내역
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


def _to_date(dt) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if hasattr(dt, 'replace'):
        return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    return dt


@router.get("/winrate", response_model=WinRateResponse, summary="승률 테스트")
async def get_win_rate(
    stock_code: Optional[str] = Query(None),
    period: str = Query("3m"),
    hold_days: int = Query(5, ge=1, le=30),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    days = PERIOD_DAYS_MAP[period]
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query: dict = {"predicted_at": {"$gte": since}}
    if stock_code:
        query["$or"] = [{"stock_code": stock_code}, {"stock_name": stock_code}]

    cursor = db.total_trading_signals.find(query).sort("predicted_at", 1)
    docs = [doc async for doc in cursor]

    if not docs:
        raise HTTPException(status_code=404, detail="해당 기간의 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name") if docs else None

    # 종목별로 그룹핑 후 포지션 추적
    # 매수 신호 → 매수, 매도 신호 → 청산, 관망 → 아무것도 안 함
    sc_docs: dict = defaultdict(list)
    for doc in docs:
        sc = doc.get("stock_code", "")
        if sc:
            sc_docs[sc].append(doc)

    trades: list = []
    realized_returns: list = []
    unrealized_positions: list = []  # 아직 청산 안 된 포지션

    today_price_map: dict = {}  # 종목별 최신 가격

    for sc, sdocs in sc_docs.items():
        position = None  # 현재 보유 포지션: {"buy_date", "buy_price"}
        latest_price = None

        for doc in sdocs:
            signal = doc.get("signal", "관망")
            dt = _to_date(doc.get("predicted_at"))
            close = doc.get("close")
            if close is None:
                continue
            close = float(close)
            latest_price = close
            date_str = dt.strftime("%Y-%m-%d")

            if signal == "매수" and position is None:
                # 매수 신호: 포지션 진입
                position = {"buy_date": date_str, "buy_price": close}

            elif signal == "매도" and position is not None:
                # 매도 신호: 포지션 청산
                ret_pct = round((close - position["buy_price"]) / position["buy_price"] * 100, 2)
                trades.append(TradeRecord(
                    buy_date=position["buy_date"],
                    buy_price=position["buy_price"],
                    sell_date=date_str,
                    sell_price=close,
                    return_pct=ret_pct,
                ))
                realized_returns.append(ret_pct)
                position = None

            # 관망은 아무것도 안 함

        # 기간 끝났는데 포지션 남아있으면 미실현 손익
        if position is not None and latest_price is not None:
            unrealized_pct = round((latest_price - position["buy_price"]) / position["buy_price"] * 100, 2)
            unrealized_positions.append(unrealized_pct)
            trades.append(TradeRecord(
                buy_date=position["buy_date"],
                buy_price=position["buy_price"],
                sell_date=None,
                sell_price=latest_price,
                unrealized_pct=unrealized_pct,
            ))

    # 결과 집계 (매수 신호 기준으로만)
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
            signal="매수→매도",
            total_signals=len(realized_returns),
            win_count=len(win),
            lose_count=len(lose),
            win_rate=round(len(win) / len(realized_returns) * 100, 1) if realized_returns else 0,
            avg_return_pct=round(sum(realized_returns) / len(realized_returns), 2),
            max_return_pct=round(max(realized_returns), 2),
            max_loss_pct=round(min(realized_returns), 2),
            cumulative_return_pct=cumulative_pct,
            unrealized_pct=avg_unrealized,
            hold_days=hold_days,
        ))
    elif unrealized_positions:
        # 청산된 거래는 없고 미실현만 있는 경우
        avg_unrealized = round(sum(unrealized_positions) / len(unrealized_positions), 2)
        results.append(WinRateResult(
            signal="매수→보유중",
            total_signals=0,
            win_count=0,
            lose_count=0,
            win_rate=0,
            avg_return_pct=0,
            max_return_pct=0,
            max_loss_pct=0,
            cumulative_return_pct=0,
            unrealized_pct=avg_unrealized,
            hold_days=hold_days,
        ))

    return WinRateResponse(
        stock_code=stock_code,
        stock_name=stock_name,
        period=period,
        results=results,
        trades=trades,
        updated_at=datetime.now(timezone.utc),
    )
