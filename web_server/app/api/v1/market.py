"""
글로벌 시장 현황 + 승률 테스트 API
- 나스닥/S&P500/환율/원유 실시간 조회 (yfinance)
- 과거 매수 신호 발생 후 실제 수익률 검증 (승률 테스트)
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import yfinance as yf
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
    change_pct: Optional[float]   # 전일 대비 등락률 (%)
    trend: str                    # "up" / "down" / "flat"


class GlobalMarketResponse(BaseModel):
    updated_at: datetime
    items: List[GlobalMarketItem]
    invest_signal: str            # "매수 우호" / "중립" / "매수 비우호"
    invest_reason: str            # 투자 판단 근거 요약


class WinRateResult(BaseModel):
    signal: str                   # 매수 / 매도 / 관망
    total_signals: int            # 총 신호 수
    win_count: int                # 수익 발생 건수
    lose_count: int               # 손실 발생 건수
    win_rate: float               # 승률 (0~100)
    avg_return_pct: float         # 평균 수익률 (%)
    max_return_pct: float         # 최대 수익률 (%)
    max_loss_pct: float           # 최대 손실률 (%)
    hold_days: int                # 보유 일수 기준


class WinRateResponse(BaseModel):
    stock_code: Optional[str]
    stock_name: Optional[str]
    period: str                   # "1m" / "3m" / "6m" / "all"
    results: List[WinRateResult]
    updated_at: datetime


# ── 글로벌 시장 현황 ───────────────────────────────────────────────────────────

GLOBAL_SYMBOLS = [
    {"symbol": "^IXIC",    "name": "나스닥"},
    {"symbol": "^GSPC",    "name": "S&P500"},
    {"symbol": "^SOX",     "name": "필라델피아 반도체"},
    {"symbol": "SOXX",     "name": "반도체 ETF"},
    {"symbol": "QQQ",      "name": "나스닥100 ETF"},
    {"symbol": "USDKRW=X", "name": "달러/원 환율"},
    {"symbol": "CL=F",     "name": "WTI 원유"},
    {"symbol": "^VIX",     "name": "VIX 공포지수"},
]


def _get_trend(change_pct: Optional[float]) -> str:
    if change_pct is None:
        return "flat"
    if change_pct >= 0.3:
        return "up"
    if change_pct <= -0.3:
        return "down"
    return "flat"


def _calc_invest_signal(items: List[GlobalMarketItem]) -> tuple:
    """글로벌 시장 지표 기반 투자 환경 판단"""
    score = 0
    reasons = []

    item_map = {i.symbol: i for i in items}

    # 나스닥 등락
    nasdaq = item_map.get("^IXIC")
    if nasdaq and nasdaq.change_pct is not None:
        if nasdaq.change_pct >= 1.0:
            score += 2
            reasons.append(f"나스닥 +{nasdaq.change_pct:.1f}% 상승")
        elif nasdaq.change_pct <= -1.0:
            score -= 2
            reasons.append(f"나스닥 {nasdaq.change_pct:.1f}% 하락")

    # VIX 공포지수
    vix = item_map.get("^VIX")
    if vix and vix.price is not None:
        if vix.price < 15:
            score += 1
            reasons.append(f"VIX {vix.price:.1f} (시장 안정)")
        elif vix.price > 25:
            score -= 2
            reasons.append(f"VIX {vix.price:.1f} (공포 구간)")

    # 달러/원 환율
    usd = item_map.get("USDKRW=X")
    if usd and usd.change_pct is not None:
        if usd.change_pct >= 1.0:
            score -= 1
            reasons.append(f"달러/원 {usd.change_pct:.1f}% 상승 (원화 약세 → 외국인 매도 압력)")
        elif usd.change_pct <= -0.5:
            score += 1
            reasons.append(f"달러/원 {usd.change_pct:.1f}% 하락 (원화 강세 → 외국인 매수 우호)")

    # 원유
    wti = item_map.get("CL=F")
    if wti and wti.change_pct is not None:
        if wti.change_pct >= 3.0:
            score -= 1
            reasons.append(f"WTI 원유 {wti.change_pct:.1f}% 급등 (인플레이션 우려)")

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
    """
    나스닥/S&P500/반도체/환율/원유/VIX 실시간 조회 후
    오늘 투자 환경 판단 신호 반환
    """
    symbols = [s["symbol"] for s in GLOBAL_SYMBOLS]

    # yfinance 비동기 실행
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None,
        lambda: yf.download(symbols, period="2d", interval="1d", group_by="ticker", progress=False)
    )

    items = []
    for info in GLOBAL_SYMBOLS:
        sym = info["symbol"]
        try:
            if len(symbols) == 1:
                close_series = data["Close"]
            else:
                close_series = data[sym]["Close"]

            closes = close_series.dropna()
            if len(closes) >= 2:
                price = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])
                change_pct = round((price - prev) / prev * 100, 2)
            elif len(closes) == 1:
                price = float(closes.iloc[-1])
                change_pct = None
            else:
                price = None
                change_pct = None
        except Exception:
            price = None
            change_pct = None

        items.append(GlobalMarketItem(
            symbol=sym,
            name=info["name"],
            price=round(price, 2) if price else None,
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
    """
    과거 AI 매수/매도 신호 발생 후 실제 수익률 검증

    - 매수 신호 발생 → hold_days 후 수익률 계산
    - 승률, 평균 수익률, 최대 수익/손실 반환
    """
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    days = PERIOD_DAYS_MAP[period]
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query: dict = {"predicted_at": {"$gte": since}}
    if stock_code:
        query["stock_code"] = stock_code

    # MongoDB에서 신호 데이터 로드
    cursor = db.total_trading_signals.find(query).sort("predicted_at", 1)
    docs = [doc async for doc in cursor]

    if not docs:
        raise HTTPException(status_code=404, detail="해당 기간의 데이터가 없습니다.")

    stock_name = docs[0].get("stock_name") if docs else None

    # 종목별 날짜순 가격 맵 생성 {stock_code: [(date, close), ...]}
    from collections import defaultdict
    price_map = defaultdict(list)
    for doc in docs:
        sc = doc.get("stock_code", "")
        dt = doc.get("predicted_at")
        close = doc.get("close")
        if sc and dt and close:
            price_map[sc].append((dt, float(close)))

    # 신호별 수익률 계산
    signal_returns = {"매수": [], "매도": [], "관망": []}

    for doc in docs:
        sc = doc.get("stock_code", "")
        signal = doc.get("signal", "관망")
        dt = doc.get("predicted_at")
        close = doc.get("close")

        if not (sc and dt and close and signal in signal_returns):
            continue

        # hold_days 후 가격 찾기
        prices = price_map[sc]
        future_prices = [
            p_close for p_dt, p_close in prices
            if timedelta(days=hold_days - 1) <= (p_dt - dt) <= timedelta(days=hold_days + 2)
        ]

        if future_prices:
            future_price = future_prices[0]
            ret_pct = (future_price - float(close)) / float(close) * 100
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
