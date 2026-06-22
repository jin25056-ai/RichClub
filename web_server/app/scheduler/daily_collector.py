"""
daily_collector.py - 매일 장 마감 후 yfinance로 OHLCV + 지표 + 신호 계산 → DB upsert
FastAPI scheduler에서 호출됨
"""
import logging
import os
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING

logger = logging.getLogger(__name__)

KOSPI_LIST = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'collect_data', 'jungho', 'kospi_list.xlsx')


def _safe(v):
    try:
        f = float(v)
        return None if (f != f) else round(f, 4)
    except:
        return None


def _calc_rsi(series: pd.Series, period=14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _calc_macd(series: pd.Series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def _calc_stoch(high, low, close, k_period=12, slowing=3, d_period=5):
    low_min = low.rolling(k_period).min()
    high_max = high.rolling(k_period).max()
    fast_k = 100 * (close - low_min) / (high_max - low_min).replace(0, np.nan)
    stoch_k = fast_k.rolling(slowing).mean()
    stoch_d = stoch_k.rolling(d_period).mean()
    return stoch_k, stoch_d


def _calc_signal(df: pd.DataFrame) -> pd.Series:
    close = df['close']
    ma5 = close.rolling(5).mean()
    macd, macd_sig = _calc_macd(close)
    stoch_k, stoch_d = _calc_stoch(df['high'], df['low'], close)
    obv = (np.sign(close.diff()) * df['volume']).fillna(0).cumsum()

    stoch_dead = (stoch_k < stoch_d) & (stoch_k.shift(1) >= stoch_d.shift(1))

    buy_mask = (
        (close > df['open']) &
        (macd > macd_sig) &
        (macd > macd_sig.shift(1)) &
        (stoch_k > stoch_d) &
        (ma5 > ma5.shift(1)) &
        (obv > obv.shift(1))
    )
    sell_mask = stoch_dead & (df['volume'] > df['volume'].shift(1)) & (close < df['open'])

    signal = pd.Series('관망', index=df.index)
    signal[sell_mask] = '매도'
    signal[buy_mask] = '매수'
    return signal


def _load_kospi_list():
    """종목 목록 로드 (xlsx)"""
    try:
        df = pd.read_excel(KOSPI_LIST)
        df['종목코드'] = df['종목코드'].astype(str).str.zfill(6)
        df['티커'] = df['종목코드'] + '.KS'
        return df[['티커', '종목명']].to_dict('records')
    except Exception as e:
        logger.error(f"종목 목록 로드 실패: {e}")
        return []


def _process_ticker_sync(ticker: str, name: str, from_date: str, to_date: str) -> list:
    """동기 처리: yfinance 수집 + 지표 계산 → doc 리스트 반환"""
    buf_start = (datetime.strptime(from_date, '%Y-%m-%d') - timedelta(days=90)).strftime('%Y-%m-%d')
    end_dt = (datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        raw = yf.download(ticker, start=buf_start, end=end_dt, interval='1d', progress=False, auto_adjust=True)
        if raw.empty:
            return []
    except Exception as e:
        logger.warning(f"{name} 다운로드 실패: {e}")
        return []

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)
    raw.columns = [c.lower() for c in raw.columns]
    raw = raw.rename(columns={'adj close': 'close'})
    raw.index = pd.to_datetime(raw.index)
    raw = raw.dropna(subset=['close'])

    if 'close' not in raw.columns:
        return []

    close = raw['close']
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    rsi = _calc_rsi(close)
    macd, macd_sig = _calc_macd(close)
    stoch_k, stoch_d = _calc_stoch(raw['high'], raw['low'], close)
    signal = _calc_signal(raw)

    mask = (raw.index >= from_date) & (raw.index <= to_date)
    docs = []
    for dt, row in raw[mask].iterrows():
        predicted_at = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
        sig = signal.get(dt, '관망')
        docs.append({
            'stock_code': name,
            'stock_name': name,
            'close':  _safe(row.get('close')),
            'open':   _safe(row.get('open')),
            'high':   _safe(row.get('high')),
            'low':    _safe(row.get('low')),
            'volume': _safe(row.get('volume')),
            'signal': sig,
            'signal_label': {'매도': 0, '매수': 1, '관망': 2}.get(sig, 2),
            'rsi':    _safe(rsi.get(dt)),
            'macd':   _safe(macd.get(dt)),
            'stoch_k': _safe(stoch_k.get(dt)),
            'stoch_d': _safe(stoch_d.get(dt)),
            'ma5':    _safe(ma5.get(dt)),
            'ma20':   _safe(ma20.get(dt)),
            'ma60':   _safe(ma60.get(dt)),
            'ma5_20_ratio':    _safe(ma5.get(dt) / ma20.get(dt)) if _safe(ma20.get(dt)) else None,
            'ma20_60_ratio':   _safe(ma20.get(dt) / ma60.get(dt)) if _safe(ma60.get(dt)) else None,
            'close_ma60_ratio': _safe(row.get('close') / ma60.get(dt)) if _safe(ma60.get(dt)) else None,
            'confidence': None,
            'conditions_met': [],
            'conditions_not_met': [],
            'feature_importance': [],
            'predicted_at': predicted_at,
            'uploaded_at': datetime.now(timezone.utc),
        })
    return docs


async def collect_daily_signals(db: AsyncIOMotorDatabase, target_date: str = None):
    """매일 장 마감 후 호출: 오늘 날짜 신호를 수집해서 DB upsert"""
    col = db.total_trading_signals
    await col.create_index([("stock_name", ASCENDING), ("predicted_at", ASCENDING)])

    today = target_date or datetime.now().strftime('%Y-%m-%d')
    logger.info(f"[daily_collector] 수집 시작: {today}")

    stocks = _load_kospi_list()
    if not stocks:
        logger.error("[daily_collector] 종목 목록 없음, 종료")
        return

    total = 0
    for i, s in enumerate(stocks):
        docs = _process_ticker_sync(s['티커'], s['종목명'], today, today)
        for doc in docs:
            result = await col.update_one(
                {'stock_name': doc['stock_name'], 'predicted_at': doc['predicted_at']},
                {'$set': doc},
                upsert=True,
            )
            if result.upserted_id or result.modified_count:
                total += 1

        if (i + 1) % 30 == 0 or (i + 1) == len(stocks):
            logger.info(f"[daily_collector] 진행 {i+1}/{len(stocks)} | upsert {total}건")

    logger.info(f"[daily_collector] 완료: {total}건 upsert ({today})")
