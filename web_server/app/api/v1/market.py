"""
글로벌 시장 현황 + 승률 테스트 + AI 실적 API
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
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
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


class HoldingItem(BaseModel):
    stock_code: str
    stock_name: str
    buy_date: str
    buy_price: float
    current_price: float
    unrealized_pct: float


class SimYearResult(BaseModel):
    year: int
    total_trades: int
    win_count: int
    lose_count: int
    win_rate: float
    avg_return_pct: float
    final_amount: float
    profit: float
    return_pct: float


class SimulationResponse(BaseModel):
    model_id: str
    principal: float
    max_stocks: int
    years: List[SimYearResult]
    total_final_amount: float
    total_profit: float
    total_return_pct: float
    updated_at: datetime


class PerformanceResponse(BaseModel):
    model_id: str
    period: str
    year: Optional[int] = None
    win_rate: float
    cumulative_return_pct: float
    total_trades: int
    win_count: int
    lose_count: int
    avg_return_pct: float
    max_return_pct: float
    max_loss_pct: float
    holdings: List[HoldingItem]
    trades: List[TradeRecord]
    updated_at: datetime


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


PERIOD_DAYS_MAP = {"1m": 30, "3m": 90, "6m": 180, "all": 99999}


def _parse_date_input(s: str) -> datetime:
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
    if ma60 is None or prev_ma60 is None:
        return False
    return float(ma60) < float(prev_ma60)


def _calc_ichimoku_span(highs: list, lows: list, idx: int) -> tuple:
    if idx >= 8:
        tenkan = (max(highs[idx-8:idx+1]) + min(lows[idx-8:idx+1])) / 2
    else:
        tenkan = None
    if idx >= 25:
        kijun = (max(highs[idx-25:idx+1]) + min(lows[idx-25:idx+1])) / 2
    else:
        kijun = None
    span_a = (tenkan + kijun) / 2 if tenkan is not None and kijun is not None else None
    if idx >= 51:
        span_b = (max(highs[idx-51:idx+1]) + min(lows[idx-51:idx+1])) / 2
    else:
        span_b = None
    return span_a, span_b


def _is_ichimoku_stagnant(close: float, span_a, span_b) -> bool:
    if span_a is None or span_b is None or close is None:
        return False
    span_a = float(span_a)
    span_b = float(span_b)
    close = float(close)
    return (span_a < span_b) and (close < span_a)


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


async def _load_ichimoku_map(db, stock_codes: list, since: datetime) -> dict:
    fetch_since = since - timedelta(days=110)
    ichimoku_map: dict = {}
    for sc in stock_codes:
        docs = [doc async for doc in db.total_trading_signals.find(
            {"stock_code": sc, "predicted_at": {"$gte": fetch_since}},
            sort=[("predicted_at", 1)],
            projection={"predicted_at": 1, "high": 1, "low": 1, "close": 1}
        )]
        if not docs:
            continue
        highs = [float(d["high"]) if d.get("high") is not None else None for d in docs]
        lows  = [float(d["low"])  if d.get("low")  is not None else None for d in docs]
        entry: dict = {}
        for i, d in enumerate(docs):
            span_a, span_b = _calc_ichimoku_span(
                [h if h is not None else 0 for h in highs],
                [l if l is not None else 0 for l in lows],
                i
            )
            date_str = _to_date(d.get("predicted_at")).strftime("%Y-%m-%d")
            entry[date_str] = (span_a, span_b)
        ichimoku_map[sc] = entry
    return ichimoku_map


async def _get_trades_for_period(db, model_id: str, since: datetime, until: datetime) -> list:
    """기간 내 전 종목 매매 기록 추출 (MA60 침체 제외)"""
    query = {
        "model_id": model_id,
        "predicted_at": {"$gte": since, "$lt": until},
    }
    docs = [doc async for doc in db.total_trading_signals.find(
        query,
        projection={"stock_code": 1, "stock_name": 1, "signal": 1, "predicted_at": 1, "close": 1, "ma60": 1}
    ).sort("predicted_at", 1)]

    sc_docs: dict = defaultdict(list)
    sc_name: dict = {}
    for doc in docs:
        sc = doc.get("stock_code", "")
        if sc:
            sc_docs[sc].append(doc)
            if sc not in sc_name:
                sc_name[sc] = doc.get("stock_name", sc)

    all_trades = []
    holdings = []

    for sc, sdocs in sc_docs.items():
        position = None
        latest_price = None
        prev_ma60 = None
        name = sc_name.get(sc, sc)

        for doc in sdocs:
            signal = doc.get("signal", "관망")
            dt = _to_date(doc.get("predicted_at"))
            close = doc.get("close")
            ma60 = doc.get("ma60")
            if close is None or float(close) <= 0:
                continue
            close = float(close)
            latest_price = close
            date_str = dt.strftime("%Y-%m-%d")
            stagnant = _ma60_falling(ma60, prev_ma60)

            if signal == "매수" and position is None and not stagnant:
                position = {"buy_date": date_str, "buy_price": close}
            elif signal == "매도" and position is not None:
                ret_pct = round((close - position["buy_price"]) / position["buy_price"] * 100, 2)
                all_trades.append(TradeRecord(
                    stock_code=sc, stock_name=name,
                    buy_date=position["buy_date"], buy_price=position["buy_price"],
                    sell_date=date_str, sell_price=close, return_pct=ret_pct,
                ))
                position = None

            if ma60 is not None:
                prev_ma60 = float(ma60)

        if position is not None and latest_price is not None:
            unrealized_pct = round((latest_price - position["buy_price"]) / position["buy_price"] * 100, 2)
            holdings.append(HoldingItem(
                stock_code=sc, stock_name=name,
                buy_date=position["buy_date"], buy_price=position["buy_price"],
                current_price=latest_price, unrealized_pct=unrealized_pct,
            ))
            all_trades.append(TradeRecord(
                stock_code=sc, stock_name=name,
                buy_date=position["buy_date"], buy_price=position["buy_price"],
                sell_date=None, sell_price=latest_price, unrealized_pct=unrealized_pct,
            ))

    return all_trades, holdings


@router.get("/performance/{model_id}", response_model=PerformanceResponse, summary="AI 모델 실적")
async def get_model_performance(
    model_id: str,
    period: str = Query("3m"),
    year: Optional[int] = Query(None),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """AI 모델 전 종목 실적"""
    if year:
        since = datetime(year, 1, 1, tzinfo=timezone.utc)
        until = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    elif period in PERIOD_DAYS_MAP:
        since = datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS_MAP[period])
        until = datetime.now(timezone.utc) + timedelta(days=1)
    else:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    all_trades, holdings = await _get_trades_for_period(db, model_id, since, until)

    if not all_trades and not holdings:
        raise HTTPException(status_code=404, detail="해당 모델의 데이터가 없습니다.")

    realized_returns = [t.return_pct for t in all_trades if t.return_pct is not None]
    win = [r for r in realized_returns if r > 0]
    lose = [r for r in realized_returns if r <= 0]
    total = len(realized_returns)
    cumulative = 1.0
    for r in realized_returns:
        cumulative *= (1 + r / 100)

    all_trades.sort(key=lambda t: t.buy_date, reverse=True)
    holdings.sort(key=lambda h: h.unrealized_pct, reverse=True)
    completed = [t for t in all_trades if t.return_pct is not None]
    open_t = [t for t in all_trades if t.unrealized_pct is not None]
    all_trades = completed[:200] + open_t

    return PerformanceResponse(
        model_id=model_id,
        period=period,
        year=year,
        win_rate=round(len(win) / total * 100, 1) if total > 0 else 0,
        cumulative_return_pct=round((cumulative - 1) * 100, 2),
        total_trades=total,
        win_count=len(win),
        lose_count=len(lose),
        avg_return_pct=round(sum(realized_returns) / total, 2) if total > 0 else 0,
        max_return_pct=round(max(realized_returns), 2) if realized_returns else 0,
        max_loss_pct=round(min(realized_returns), 2) if realized_returns else 0,
        holdings=holdings,
        trades=all_trades,
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/simulation/{model_id}", response_model=SimulationResponse, summary="AI 모델 포트폴리오 시뮬레이션")
async def get_simulation(
    model_id: str,
    principal: float = Query(10000000, description="투자 원금"),
    max_stocks: int = Query(10, ge=1, le=50, description="동시 보유 최대 종목 수"),
    year: Optional[int] = Query(None, description="특정 연도 (없으면 전체)"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """
    포트폴리오 시뮬레이션
    - 투자금을 max_stocks로 균등 분배
    - 매수 시그널마다 종목당 투자금으로 진입
    - 매도 시그널에 청산, 손익 반영
    - 동시 보유 max_stocks 초과 시 신규 매수 스킵
    """
    years_to_sim = [year] if year else list(range(2021, datetime.now().year + 1))
    per_stock = principal / max_stocks

    year_results: list = []
    running_amount = principal

    for y in years_to_sim:
        since = datetime(y, 1, 1, tzinfo=timezone.utc)
        until = datetime(y + 1, 1, 1, tzinfo=timezone.utc)

        query = {
            "model_id": model_id,
            "predicted_at": {"$gte": since, "$lt": until},
        }
        docs = [doc async for doc in db.total_trading_signals.find(
            query,
            projection={"stock_code": 1, "stock_name": 1, "signal": 1, "predicted_at": 1, "close": 1, "ma60": 1}
        ).sort("predicted_at", 1)]

        if not docs:
            continue

        # 종목별로 그룹화
        sc_docs: dict = defaultdict(list)
        for doc in docs:
            sc = doc.get("stock_code", "")
            if sc:
                sc_docs[sc].append(doc)

        # 날짜별 이벤트 수집 (매수/매도)
        events: list = []
        for sc, sdocs in sc_docs.items():
            position = None
            prev_ma60 = None
            for doc in sdocs:
                signal = doc.get("signal", "관망")
                dt = _to_date(doc.get("predicted_at"))
                close = doc.get("close")
                ma60 = doc.get("ma60")
                if close is None or float(close) <= 0:
                    continue
                close = float(close)
                date_str = dt.strftime("%Y-%m-%d")
                stagnant = _ma60_falling(ma60, prev_ma60)

                if signal == "매수" and position is None and not stagnant:
                    position = {"buy_date": date_str, "buy_price": close, "sc": sc}
                    events.append({"date": date_str, "type": "buy", "sc": sc, "price": close})
                elif signal == "매도" and position is not None:
                    events.append({"date": date_str, "type": "sell", "sc": sc,
                                   "buy_price": position["buy_price"], "sell_price": close})
                    position = None

                if ma60 is not None:
                    prev_ma60 = float(ma60)

        # 날짜순 정렬 후 시뮬레이션
        events.sort(key=lambda e: e["date"])
        holdings_map: dict = {}  # sc -> 투자금
        year_profit = 0.0
        win_count = 0
        lose_count = 0
        returns: list = []

        for ev in events:
            sc = ev["sc"]
            if ev["type"] == "buy":
                if sc not in holdings_map and len(holdings_map) < max_stocks:
                    holdings_map[sc] = per_stock
            elif ev["type"] == "sell":
                if sc in holdings_map:
                    invested = holdings_map.pop(sc)
                    ret_pct = (ev["sell_price"] - ev["buy_price"]) / ev["buy_price"]
                    profit = invested * ret_pct
                    year_profit += profit
                    returns.append(ret_pct * 100)
                    if profit > 0:
                        win_count += 1
                    else:
                        lose_count += 1

        total_trades = win_count + lose_count
        final = running_amount + year_profit
        ret_pct_year = round((year_profit / running_amount) * 100, 2) if running_amount > 0 else 0

        year_results.append(SimYearResult(
            year=y,
            total_trades=total_trades,
            win_count=win_count,
            lose_count=lose_count,
            win_rate=round(win_count / total_trades * 100, 1) if total_trades > 0 else 0,
            avg_return_pct=round(sum(returns) / len(returns), 2) if returns else 0,
            final_amount=round(final, 0),
            profit=round(year_profit, 0),
            return_pct=ret_pct_year,
        ))
        running_amount = final

    total_profit = running_amount - principal
    total_return_pct = round((total_profit / principal) * 100, 2) if principal > 0 else 0

    return SimulationResponse(
        model_id=model_id,
        principal=principal,
        max_stocks=max_stocks,
        years=year_results,
        total_final_amount=round(running_amount, 0),
        total_profit=round(total_profit, 0),
        total_return_pct=total_return_pct,
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/winrate", response_model=WinRateResponse, summary="승률 테스트 (AI) - 침체구간 제외")
async def get_win_rate(
    stock_code: Optional[str] = Query(None),
    period: str = Query("3m"),
    hold_days: int = Query(5, ge=1, le=30),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """AI 매수 + MA60 침체 제외 + AI 매도"""
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    since = _parse_date_input(start_date) if start_date else datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS_MAP[period])
    until = (_parse_date_input(end_date) + timedelta(days=1)) if end_date else datetime.now(timezone.utc) + timedelta(days=1)

    query: dict = {"predicted_at": {"$gte": since, "$lt": until}}
    if model_id:
        query["model_id"] = model_id
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

    ichimoku_map = await _load_ichimoku_map(db, list(sc_docs.keys()), since)

    trades: list = []
    realized_returns: list = []
    unrealized_positions: list = []

    for sc, sdocs in sc_docs.items():
        position = None
        latest_price = None
        prev_ma60 = None
        ichi = ichimoku_map.get(sc, {})

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

            span_a, span_b = ichi.get(date_str, (None, None))
            stagnant = _is_ichimoku_stagnant(close, span_a, span_b) or _ma60_falling(ma60, prev_ma60)

            if signal == "매수" and position is None and not stagnant:
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
                                   "매수(AI+침체제외)→매도(AI)")


@router.get("/winrate/simple", response_model=WinRateResponse, summary="승률 테스트 (AI 매수 + 5일선 매도) - MA60 하락 제외")
async def get_win_rate_simple(
    stock_code: Optional[str] = Query(None),
    period: str = Query("3m"),
    hold_days: int = Query(5, ge=1, le=30),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """AI 매수 + MA60 침체 제외 + 5일선 꺾임 매도"""
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    since = _parse_date_input(start_date) if start_date else datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS_MAP[period])
    until = (_parse_date_input(end_date) + timedelta(days=1)) if end_date else datetime.now(timezone.utc) + timedelta(days=1)

    query: dict = {"predicted_at": {"$gte": since, "$lt": until}}
    if model_id:
        query["model_id"] = model_id
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

    ichimoku_map = await _load_ichimoku_map(db, list(sc_docs.keys()), since)

    trades: list = []
    realized_returns: list = []
    unrealized_positions: list = []

    for sc, sdocs in sc_docs.items():
        position = None
        latest_price = None
        prev_ma5 = None
        prev_ma60 = None
        ichi = ichimoku_map.get(sc, {})

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

            span_a, span_b = ichi.get(date_str, (None, None))
            stagnant = _is_ichimoku_stagnant(close, span_a, span_b) or _ma60_falling(ma60, prev_ma60)
            ma5_turning_down = (ma5 is not None and prev_ma5 is not None
                                and float(ma5) < float(prev_ma5))

            if signal == "매수" and position is None and not stagnant:
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
                                   "매수(AI+침체제외)→매도(5일선꺾임)")


@router.get("/winrate/combined", response_model=WinRateResponse, summary="승률 테스트 (AI+정배열 매수) - MA60 하락 제외")
async def get_win_rate_combined(
    stock_code: Optional[str] = Query(None),
    period: str = Query("3m"),
    hold_days: int = Query(5, ge=1, le=30),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """AI + MA 정배열 매수 + AI or MA 역배열 매도"""
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    since = _parse_date_input(start_date) if start_date else datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS_MAP[period])
    until = (_parse_date_input(end_date) + timedelta(days=1)) if end_date else datetime.now(timezone.utc) + timedelta(days=1)

    query: dict = {"predicted_at": {"$gte": since, "$lt": until}}
    if model_id:
        query["model_id"] = model_id
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

    ichimoku_map = await _load_ichimoku_map(db, list(sc_docs.keys()), since)

    trades: list = []
    realized_returns: list = []
    unrealized_positions: list = []

    for sc, sdocs in sc_docs.items():
        position = None
        latest_price = None
        prev_ma60 = None
        ichi = ichimoku_map.get(sc, {})

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

            span_a, span_b = ichi.get(date_str, (None, None))
            stagnant = _is_ichimoku_stagnant(close, span_a, span_b) or _ma60_falling(ma60, prev_ma60)
            ma_bullish = (ma5 is not None and ma20 is not None and ma60 is not None
                          and float(ma5) > float(ma20) > float(ma60))
            ma_bearish = (ma5 is not None and ma20 is not None and ma60 is not None
                          and float(ma5) < float(ma20) < float(ma60))

            if signal == "매수" and ma_bullish and position is None and not stagnant:
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
                                   "매수(AI+정배열+침체제외)→매도(AI or 역배열)")


@router.get("/winrate/indicator", response_model=WinRateResponse, summary="승률 테스트 (지표만) - AI 모델 무관")
async def get_win_rate_indicator(
    stock_code: Optional[str] = Query(None),
    period: str = Query("3m"),
    hold_days: int = Query(5, ge=1, le=30),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """지표만 승률 테스트 - AI 모델과 무관하게 MA 정배열/역배열만 사용"""
    if period not in PERIOD_DAYS_MAP:
        raise HTTPException(status_code=400, detail="period는 1m / 3m / 6m / all 중 하나")

    since = _parse_date_input(start_date) if start_date else datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS_MAP[period])
    until = (_parse_date_input(end_date) + timedelta(days=1)) if end_date else datetime.now(timezone.utc) + timedelta(days=1)

    query: dict = {
        "predicted_at": {"$gte": since, "$lt": until},
        "model_id": "ju-model-v2",
    }
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

    ichimoku_map = await _load_ichimoku_map(db, list(sc_docs.keys()), since)

    trades: list = []
    realized_returns: list = []
    unrealized_positions: list = []

    for sc, sdocs in sc_docs.items():
        position = None
        latest_price = None
        prev_in_bullish = False
        prev_ma60 = None
        ichi = ichimoku_map.get(sc, {})

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

            span_a, span_b = ichi.get(date_str, (None, None))
            stagnant = _is_ichimoku_stagnant(close, span_a, span_b) or _ma60_falling(ma60, prev_ma60)
            ma_bullish = (ma5 is not None and ma20 is not None and ma60 is not None
                          and float(ma5) > float(ma20) > float(ma60))
            ma_bearish = (ma5 is not None and ma20 is not None and ma60 is not None
                          and float(ma5) < float(ma20) < float(ma60))

            if ma_bullish and not prev_in_bullish and position is None and not stagnant:
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
                                   "매수(MA정배열+침체제외)→매도(MA역배열)")
