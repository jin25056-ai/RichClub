"""
글로벌 시장 현황 + 승률 테스트 + AI 실적 API
- Yahoo Finance 429 방지: 서버 메모리 캐시 10분
- MA60 하락 구간: 매수 금지 (침체 구간)
"""
import asyncio
import random
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

_perf_cache: dict = {}
_PERF_CACHE_TTL = 300

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
    """기간 내 전 종목 매매 기록 추출 (MA60 침체 제외)

    aggregation pipeline으로 종목별 배열을 서버 사이드에서 미리 그룹필하고 필요한 필드만 프로젝션해
    네트워크 전송량과 BSON 오버헤드를 줄임.
    """
    pipeline = [
        {"$match": {
            "model_id": model_id,
            "predicted_at": {"$gte": since, "$lt": until},
            "stock_code": {"$ne": None, "$ne": ""},
        }},
        {"$sort": {"predicted_at": 1}},
        {"$group": {
            "_id": "$stock_code",
            "stock_name": {"$first": "$stock_name"},
            "rows": {"$push": {
                "d": "$predicted_at",
                "s": "$signal",
                "c": "$close",
                "m": "$ma60",
            }},
        }},
    ]

    all_trades = []
    holdings = []

    async for doc in db.total_trading_signals.aggregate(pipeline, allowDiskUse=True):
        sc = doc["_id"]
        name = doc.get("stock_name", sc)
        rows = doc.get("rows", [])

        position = None
        latest_price = None
        prev_ma60 = None

        for row in rows:
            signal = row.get("s", "관망")
            close = row.get("c")
            ma60 = row.get("m")
            if close is None or float(close) <= 0:
                continue
            close = float(close)
            latest_price = close
            dt = _to_date(row.get("d"))
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
    cache_key = f"perf:{model_id}:{period}:{year}"
    cached = _perf_cache.get(cache_key)
    if cached and (time.time() - cached["ts"]) < _PERF_CACHE_TTL:
        return cached["data"]

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
    cumulative_pct = round(sum(realized_returns), 2) if realized_returns else 0.0

    all_trades.sort(key=lambda t: t.buy_date, reverse=True)
    holdings.sort(key=lambda h: h.unrealized_pct, reverse=True)
    completed = [t for t in all_trades if t.return_pct is not None]
    open_t = [t for t in all_trades if t.unrealized_pct is not None]
    all_trades = completed + open_t

    response = PerformanceResponse(
        model_id=model_id,
        period=period,
        year=year,
        win_rate=round(len(win) / total * 100, 1) if total > 0 else 0,
        cumulative_return_pct=cumulative_pct,
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
    _perf_cache[cache_key] = {"data": response, "ts": time.time()}
    return response


async def _get_seo_simulation_year(db, model_id: str, since: datetime, until: datetime,
                                    running_amount: float, max_slots: int = 4,
                                    reg_score_threshold: float = 0.05):
    """
    seo-model-v1/v2 원본 파이썬 시뮬레이션(simulation_rev1.py, lgb_regressor 기준)와 동일한 로직.
    - 매수: reg_score > threshold 이고 target != 3 이고 above_max_volume_profile == 1인 종목
    - 매도: 종가가 5일선(ma5) 아래로 떨어질 때 (AI 신호 무관)
    - 동시 보유 종목수 제한: max_slots (원본 기본값 4)
    - 자금 배분: 매 순간 cash / available_slots로 동적 재계산
    - 같은 날 여러 매수 후보 중 reg_score 높은 순으로 우선 매수
    반환: (최종잔액, 승, 패, 총거래, 수익률리스트, trades)
    """
    pipeline = [
        {"$match": {
            "model_id": model_id,
            "predicted_at": {"$gte": since, "$lt": until},
            "stock_code": {"$ne": None, "$ne": ""},
        }},
        {"$sort": {"predicted_at": 1}},
        {"$group": {
            "_id": "$stock_code",
            "stock_name": {"$first": "$stock_name"},
            "rows": {"$push": {
                "d": "$predicted_at",
                "c": "$close",
                "ma5": "$ma5",
                "score": "$reg_score",
                "vp": "$above_max_volume_profile",
                "target": "$target",
            }},
        }},
    ]

    by_date: dict = defaultdict(dict)  # date_str -> {sc: row}
    sc_name: dict = {}
    async for doc in db.total_trading_signals.aggregate(pipeline, allowDiskUse=True):
        sc = doc["_id"]
        sc_name[sc] = doc.get("stock_name", sc)
        for row in doc.get("rows", []):
            dt = _to_date(row.get("d"))
            date_str = dt.strftime("%Y-%m-%d")
            by_date[date_str][sc] = row

    if not by_date:
        return running_amount, 0, 0, 0, [], []

    all_dates = sorted(by_date.keys())
    cash = running_amount
    portfolio: dict = {}  # sc -> {buy_price, shares, buy_total_amt, buy_date}
    win_count = 0
    lose_count = 0
    returns: list = []
    trades: list = []

    for date_str in all_dates:
        day_rows = by_date[date_str]

        # [1] 매도: 종가 < ma5 이면 매도
        to_sell = []
        for sc, info in list(portfolio.items()):
            row = day_rows.get(sc)
            if not row:
                continue
            close = row.get("c")
            ma5 = row.get("ma5")
            if close is None:
                continue
            close = float(close)
            ma5_val = float(ma5) if ma5 is not None else close

            if close < ma5_val:
                sell_total = close * info["shares"]
                cash += sell_total
                profit = sell_total - info["buy_total_amt"]
                ret_pct = (close / info["buy_price"] - 1) * 100
                returns.append(ret_pct)
                if profit > 0:
                    win_count += 1
                else:
                    lose_count += 1
                trades.append(TradeRecord(
                    stock_code=sc, stock_name=sc_name.get(sc, sc),
                    buy_date=info["buy_date"], buy_price=info["buy_price"],
                    sell_date=date_str, sell_price=close, return_pct=round(ret_pct, 2),
                ))
                to_sell.append(sc)

        for sc in to_sell:
            del portfolio[sc]

        # [2] 매수: reg_score > threshold, target != 3, vp == 1
        candidates = []
        for sc, row in day_rows.items():
            if sc in portfolio:
                continue
            score = row.get("score")
            target = row.get("target")
            vp = row.get("vp")
            close = row.get("c")
            if score is None or close is None:
                continue
            if float(score) <= reg_score_threshold:
                continue
            if target is not None and int(target) == 3:
                continue
            if vp is not None and int(vp) != 1:
                continue
            candidates.append((sc, float(score), float(close)))

        candidates.sort(key=lambda x: x[1], reverse=True)

        for sc, score, buy_price in candidates:
            available_slots = max_slots - len(portfolio)
            if available_slots <= 0:
                break
            allocated_cash = cash / available_slots
            if allocated_cash < 10000:
                continue
            shares = int(allocated_cash // buy_price)
            if shares <= 0:
                continue
            buy_total = buy_price * shares
            cash -= buy_total
            portfolio[sc] = {"buy_price": buy_price, "shares": shares, "buy_total_amt": buy_total, "buy_date": date_str}

    # 마지막 날 강제 청산
    if all_dates and portfolio:
        last_rows = by_date[all_dates[-1]]
        for sc, info in list(portfolio.items()):
            row = last_rows.get(sc)
            close = float(row["c"]) if row and row.get("c") is not None else info["buy_price"]
            sell_total = close * info["shares"]
            cash += sell_total
            profit = sell_total - info["buy_total_amt"]
            ret_pct = (close / info["buy_price"] - 1) * 100
            returns.append(ret_pct)
            if profit > 0:
                win_count += 1
            else:
                lose_count += 1
            trades.append(TradeRecord(
                stock_code=sc, stock_name=sc_name.get(sc, sc),
                buy_date=info["buy_date"], buy_price=info["buy_price"],
                sell_date=all_dates[-1], sell_price=close, return_pct=round(ret_pct, 2),
            ))
        portfolio.clear()

    return cash, win_count, lose_count, win_count + lose_count, returns, trades


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
    포트폴리오 시뮬레이션.
    - ju-model-v2: 기존 방식 (AI 신호 기반 매수/매도, 고정 배분)
    - seo-model-v1/v2: 원본 파이썬 시뮬레이션과 동일한 로직 (pred_score 임계값 매수, 5일선 이탈 매도, 동적 배분)
    """
    cache_key = f"sim:{model_id}:{principal}:{max_stocks}:{year}"
    cached = _perf_cache.get(cache_key)
    if cached and (time.time() - cached["ts"]) < _PERF_CACHE_TTL:
        return cached["data"]

    years_to_sim = [year] if year else list(range(2021, datetime.now().year + 1))

    is_seo_model = model_id.startswith("seo-model")

    year_results: list = []
    running_amount = principal

    if is_seo_model:
        for y in years_to_sim:
            since = datetime(y, 1, 1, tzinfo=timezone.utc)
            until = datetime(y + 1, 1, 1, tzinfo=timezone.utc)

            final, win_count, lose_count, total_trades, returns, _trades = await _get_seo_simulation_year(
                db, model_id, since, until, running_amount, max_slots=max_stocks
            )
            if total_trades == 0 and final == running_amount:
                continue

            year_profit = final - running_amount
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

        return_response = SimulationResponse(
            model_id=model_id,
            principal=principal,
            max_stocks=max_stocks,
            years=year_results,
            total_final_amount=round(running_amount, 0),
            total_profit=round(total_profit, 0),
            total_return_pct=total_return_pct,
            updated_at=datetime.now(timezone.utc),
        )
        _perf_cache[cache_key] = {"data": return_response, "ts": time.time()}
        return return_response

    per_stock = principal / max_stocks

    year_results: list = []
    running_amount = principal

    for y in years_to_sim:
        since = datetime(y, 1, 1, tzinfo=timezone.utc)
        until = datetime(y + 1, 1, 1, tzinfo=timezone.utc)

        pipeline = [
            {"$match": {
                "model_id": model_id,
                "predicted_at": {"$gte": since, "$lt": until},
                "stock_code": {"$ne": None, "$ne": ""},
            }},
            {"$sort": {"predicted_at": 1}},
            {"$group": {
                "_id": "$stock_code",
                "rows": {"$push": {
                    "d": "$predicted_at",
                    "s": "$signal",
                    "c": "$close",
                    "m": "$ma60",
                }},
            }},
        ]

        sc_docs: dict = {}
        async for doc in db.total_trading_signals.aggregate(pipeline, allowDiskUse=True):
            sc_docs[doc["_id"]] = doc.get("rows", [])

        if not sc_docs:
            continue

        # 날짜별 이벤트 수집
        events: list = []
        for sc, rows in sc_docs.items():
            position = None
            prev_ma60 = None
            for row in rows:
                signal = row.get("s", "관망")
                close = row.get("c")
                ma60 = row.get("m")
                if close is None or float(close) <= 0:
                    continue
                close = float(close)
                dt = _to_date(row.get("d"))
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

        # 날짜별 매수/매도 분리
        buy_by_date: dict = defaultdict(list)
        sell_by_date: dict = defaultdict(list)
        for ev in events:
            if ev["type"] == "buy":
                buy_by_date[ev["date"]].append(ev)
            else:
                sell_by_date[ev["date"]].append(ev)

        all_dates = sorted(set(list(buy_by_date.keys()) + list(sell_by_date.keys())))

        holdings_map: dict = {}  # sc -> {"invested": float, "buy_price": float}
        year_profit = 0.0
        win_count = 0
        lose_count = 0
        returns: list = []

        for date_str in all_dates:
            # 매도 먼저 처리
            for ev in sell_by_date.get(date_str, []):
                sc = ev["sc"]
                if sc in holdings_map:
                    h = holdings_map.pop(sc)
                    ret_pct = (ev["sell_price"] - ev["buy_price"]) / ev["buy_price"]
                    profit = h["invested"] * ret_pct
                    year_profit += profit
                    returns.append(ret_pct * 100)
                    if profit > 0:
                        win_count += 1
                    else:
                        lose_count += 1

            # 매수: 같은 날 신호 랜덤 셔플 후 순서대로 진입 시도
            buys = buy_by_date.get(date_str, [])
            if buys:
                random.shuffle(buys)
                for ev in buys:
                    sc = ev["sc"]
                    buy_price = ev["price"]
                    if sc in holdings_map:
                        continue
                    if len(holdings_map) >= max_stocks:
                        break
                    # 주가가 종목당 투자금보다 비싸면 살 수 없음
                    if buy_price > per_stock:
                        continue
                    # 실제 매수: 살 수 있는 주수 * 주가 (잔돈은 현금으로)
                    shares = int(per_stock // buy_price)
                    if shares <= 0:
                        continue
                    actual_invested = shares * buy_price
                    holdings_map[sc] = {"invested": actual_invested, "buy_price": buy_price}

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

    return_response = SimulationResponse(
        model_id=model_id,
        principal=principal,
        max_stocks=max_stocks,
        years=year_results,
        total_final_amount=round(running_amount, 0),
        total_profit=round(total_profit, 0),
        total_return_pct=total_return_pct,
        updated_at=datetime.now(timezone.utc),
    )
    _perf_cache[cache_key] = {"data": return_response, "ts": time.time()}
    return return_response


@router.get("/simulation-detail/{model_id}", response_model=WinRateResponse, summary="AI 시뮬레이션 연도별 상세 (실제 체결 거래 리스트)")
async def get_simulation_detail(
    model_id: str,
    year: int = Query(...),
    max_stocks: int = Query(10, ge=1, le=200),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """
    시뮬레이션이 실제로 체결한 거래 리스트를 반환한다. (AI 신호 기반 전체 거래와는 다름)
    seo-model 계열은 reg_score 기준 시뮬레이션, 그 외는 빈 거래 리스트 반환.
    """
    since = datetime(year, 1, 1, tzinfo=timezone.utc)
    until = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

    if not model_id.startswith("seo-model"):
        raise HTTPException(status_code=400, detail="현재 seo-model 계열만 지원합니다.")

    _, win_count, lose_count, total_trades, returns, trades = await _get_seo_simulation_year(
        db, model_id, since, until, running_amount=10_000_000, max_slots=max_stocks
    )

    trades.sort(key=lambda t: t.buy_date, reverse=True)
    win = [r for r in returns if r > 0]

    return WinRateResponse(
        stock_code=None, stock_name=None, period=str(year),
        results=[WinRateResult(
            signal="시뮬레이션",
            total_signals=total_trades,
            win_count=win_count, lose_count=lose_count,
            win_rate=round(len(win) / len(returns) * 100, 1) if returns else 0,
            avg_return_pct=round(sum(returns) / len(returns), 2) if returns else 0,
            max_return_pct=round(max(returns), 2) if returns else 0,
            max_loss_pct=round(min(returns), 2) if returns else 0,
            cumulative_return_pct=round(sum(returns), 2) if returns else 0,
            unrealized_pct=None,
            hold_days=0,
        )],
        trades=trades,
        updated_at=datetime.now(timezone.utc),
    )


_INDEX_CODES_CACHE: dict = {"codes": None, "ts": 0}
_INDEX_CACHE_TTL = 3600


def _load_index_codes() -> set:
    """KOSPI200 + KOSDAQ150 종목코드 로드 (1시간 캐시)."""
    now = time.time()
    if _INDEX_CODES_CACHE["codes"] is not None and (now - _INDEX_CODES_CACHE["ts"]) < _INDEX_CACHE_TTL:
        return _INDEX_CODES_CACHE["codes"]

    import pandas as pd

    codes: set = set()
    base_dir = "/app/collect_data/seojin"
    for filename in ["KOSPI200.csv", "KOSDAQ150.csv"]:
        path = f"{base_dir}/{filename}"
        try:
            df = pd.read_csv(path, encoding="cp949", dtype=str)
            if len(df.columns) == 1 and "," in df.columns[0]:
                col = df.columns[0]
                df[["stk_cd", "_"]] = df[col].str.split(",", n=1, expand=True)
            else:
                code_col = next(
                    (c for c in df.columns if c in ["stk_cd", "ticker", "code", "종목코드", "단축코드"]),
                    df.columns[0]
                )
                df["stk_cd"] = df[code_col].astype(str)
            df["stk_cd"] = df["stk_cd"].str.replace(".0", "", regex=False).str.strip().str.zfill(6)
            codes.update(df["stk_cd"].tolist())
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).warning(f"[recommend] {filename} 로드 실패: {e}")

    _INDEX_CODES_CACHE["codes"] = codes
    _INDEX_CODES_CACHE["ts"] = now
    return codes


class RecommendItem(BaseModel):
    stock_code: str
    stock_name: str
    model_name: str
    pred_score: float
    close: Optional[float]
    market_group: Optional[str] = None


class RecommendResponse(BaseModel):
    date: str
    total: int
    items: List[RecommendItem]
    updated_at: datetime


@router.get("/recommend", response_model=RecommendResponse, summary="AI 추천 종목 (KOSPI200+KOSDAQ150 기준)")
async def get_recommend(
    target_date: Optional[str] = Query(None, description="조회 날짜 (YYYY-MM-DD, 기본: 오늘)"),
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """
    방금 준 combotest 스크립트와 동일한 조건으로 추천 종목 추출.

    - 대상: KOSPI200 + KOSDAQ150 종목만
    - seo-model-v2 lgb_classifier / xgb_classifier: pred_score > 0.70 + target != 3 + above_max_volume_profile == 1
    - seo-model-v2 lgb_regressor: reg_score > 0.05 + target != 3 + above_max_volume_profile == 1
    - 결과: pred_score (또는 reg_score) 내림차순 정렬
    """
    if target_date:
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식은 YYYY-MM-DD")
        since = dt.replace(tzinfo=timezone.utc)
        until = since + timedelta(days=1)
    else:
        # 오늘 날짜 기준으로 조회하되, 없으면 가장 최근 날짜로 폴백
        dt = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        since = dt
        until = since + timedelta(days=1)

    index_codes = _load_index_codes()
    if not index_codes:
        raise HTTPException(status_code=503, detail="KOSPI200/KOSDAQ150 종목 목록 로드 실패")

    # 해당 날짜의 seo-model-v2 데이터 조회 (vp/target 값이 있는 CSV 기반 데이터만)
    async def _query_recommend(s, u):
        return [doc async for doc in db.total_trading_signals.find(
            {
                "model_id": "seo-model-v2",
                "predicted_at": {"$gte": s, "$lt": u},
                "stock_code": {"$in": list(index_codes)},
                "above_max_volume_profile": {"$in": [0, 1]},  # CSV 기반 데이터만 (None 제외)
            },
            projection={
                "stock_code": 1, "stock_name": 1,
                "pred_score": 1, "reg_score": 1,
                "target": 1, "above_max_volume_profile": 1, "close": 1,
                "predicted_at": 1,
            }
        )]

    docs = await _query_recommend(since, until)

    # 오늘 데이터 없으면 가장 최근 날짜로 폴백
    if not docs and not target_date:
        latest = await db.total_trading_signals.find_one(
            {"model_id": "seo-model-v2", "above_max_volume_profile": {"$in": [0, 1]}},
            sort=[("predicted_at", -1)],
            projection={"predicted_at": 1},
        )
        if latest:
            ld = latest["predicted_at"].replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
            docs = await _query_recommend(ld, ld + timedelta(days=1))
            since = ld

    # target==3(침체) 제외 + vp==1인 것만 + reg_score 양수 우선, 상위 20개
    scored: list = []
    for doc in docs:
        code = doc.get("stock_code", "")
        name = doc.get("stock_name", code)
        pred_score = doc.get("pred_score")
        reg_score = doc.get("reg_score")
        target = doc.get("target")
        vp = doc.get("above_max_volume_profile")
        close = doc.get("close")

        if target is not None and int(target) == 3:
            continue
        if vp is not None and int(vp) != 1:
            continue

        # reg_score 양수 우선, 없으면 pred_score
        if reg_score is not None and float(reg_score) > 0:
            scored.append(RecommendItem(
                stock_code=code, stock_name=name,
                model_name="lgb_regressor",
                pred_score=round(float(reg_score), 6),
                close=close,
            ))
        elif pred_score is not None and float(pred_score) > 0:
            scored.append(RecommendItem(
                stock_code=code, stock_name=name,
                model_name="lgb_classifier+xgb_classifier",
                pred_score=round(float(pred_score), 6),
                close=close,
            ))

    # 중복 제거 후 score 내림차순 상위 20개
    seen: dict = {}
    for item in scored:
        key = item.stock_code
        if key not in seen or item.pred_score > seen[key].pred_score:
            seen[key] = item

    result = sorted(seen.values(), key=lambda x: x.pred_score, reverse=True)[:20]

    return RecommendResponse(
        date=since.strftime("%Y-%m-%d"),
        total=len(result),
        items=result,
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
