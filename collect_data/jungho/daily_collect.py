"""
daily_collect.py - 매일 장 마감 후 오늘 날짜 OHLCV + 지표 계산 + AI 신호 → DB upsert

흐름:
  1. kospi_list.xlsx에서 종목 목록 읽기
  2. yfinance로 최근 90일 OHLCV 수집 (MA/RSI/MACD 계산용 버퍼)
  3. 기술 지표 계산 (MA5/MA20/MA60, RSI, MACD, 스토캐스틱, OBV)
  4. 간단 규칙 기반 신호 생성 (매수/매도/관망)
  5. 오늘 날짜 데이터만 DB upsert (중복 방지)

실행:
  python daily_collect.py                    # 오늘 날짜만
  python daily_collect.py --date 2026-06-20  # 특정 날짜
  python daily_collect.py --from 2026-06-18  # 특정 날짜부터 오늘까지

환경변수:
  MONGODB_URI, MONGODB_DB
"""
import os
import sys
import argparse
import logging
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

KOSPI_LIST = os.path.join(os.path.dirname(__file__), 'kospi_list.xlsx')

def _get_col() -> 'Collection':
    load_dotenv()
    uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or ""
    db_name = os.getenv("MONGODB_DB") or os.getenv("DB_NAME") or "richclub"
    client = MongoClient(uri)
    return client[db_name]["total_trading_signals"]

def _safe(v):
    try:
        f = float(v)
        return None if (f != f) else round(f, 4)  # NaN 체크
    except:
        return None

def calc_rsi(series: pd.Series, period=14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_macd(series: pd.Series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def calc_stoch(high, low, close, k_period=12, d_period=3, slowing=5):
    low_min = low.rolling(k_period).min()
    high_max = high.rolling(k_period).max()
    fast_k = 100 * (close - low_min) / (high_max - low_min).replace(0, np.nan)
    stoch_k = fast_k.rolling(slowing).mean()
    stoch_d = stoch_k.rolling(d_period).mean()
    return stoch_k, stoch_d

def calc_signal(df: pd.DataFrame) -> pd.Series:
    """규칙 기반 매수/매도/관망 신호"""
    close = df['close']
    high  = df['high']
    low   = df['low']
    vol   = df['volume']

    ma5  = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()

    macd, macd_sig = calc_macd(close)
    stoch_k, stoch_d = calc_stoch(high, low, close)
    obv = (np.sign(close.diff()) * vol).fillna(0).cumsum()
    rsi = calc_rsi(close)

    # 스토캐스틱 데드크로스
    stoch_dead = (stoch_k < stoch_d) & (stoch_k.shift(1) >= stoch_d.shift(1))
    # VIX는 여기서 없으니 패닉 조건 제외

    buy_mask = (
        (close > df['open']) &              # 양봉
        (macd > macd_sig) &                 # MACD 정배열
        (macd > macd_sig.shift(1)) &        # MACD 상승
        (stoch_k > stoch_d) &               # 스토캐스틱 정배열
        (ma5 > ma5.shift(1)) &              # MA5 상승
        (obv > obv.shift(1))                # OBV 상승
    )

    sell_mask = (
        stoch_dead &
        (vol > vol.shift(1)) &
        (close < df['open'])                # 음봉
    )

    signal = pd.Series('관망', index=df.index)
    signal[sell_mask] = '매도'
    signal[buy_mask]  = '매수'
    return signal

def process_ticker(ticker: str, name: str, from_date: str, to_date: str, col) -> int:
    """종목 하나 처리 → upsert 건수 반환"""
    # 지표 계산용 버퍼 90일 추가
    buf_start = (datetime.strptime(from_date, '%Y-%m-%d') - timedelta(days=90)).strftime('%Y-%m-%d')
    end_dt    = (datetime.strptime(to_date,   '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        raw = yf.download(ticker, start=buf_start, end=end_dt, interval='1d', progress=False, auto_adjust=True)
        if raw.empty:
            return 0
    except Exception as e:
        logger.warning(f"{name} 다운로드 실패: {e}")
        return 0

    # MultiIndex 처리
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)

    raw.columns = [c.lower() for c in raw.columns]
    raw = raw.rename(columns={'adj close': 'close'})
    raw.index = pd.to_datetime(raw.index)

    if 'close' not in raw.columns:
        return 0

    raw = raw.dropna(subset=['close'])

    # 지표 계산
    close = raw['close']
    ma5   = close.rolling(5).mean()
    ma20  = close.rolling(20).mean()
    ma60  = close.rolling(60).mean()
    rsi   = calc_rsi(close)
    macd, macd_sig = calc_macd(close)
    stoch_k, stoch_d = calc_stoch(raw['high'], raw['low'], close)
    obv   = (np.sign(close.diff()) * raw['volume']).fillna(0).cumsum()
    signal = calc_signal(raw.assign(close=close))

    # 대상 날짜만 필터
    mask = (raw.index >= from_date) & (raw.index <= to_date)
    target = raw[mask]
    if target.empty:
        return 0

    upserted = 0
    for dt, row in target.iterrows():
        date_str = dt.strftime('%Y-%m-%d')
        predicted_at = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)

        sig = signal.get(dt, '관망')
        sig_label = {'매도': 0, '매수': 1, '관망': 2}.get(sig, 2)

        doc = {
            'stock_code': name,
            'stock_name': name,
            'close':  _safe(row.get('close')),
            'open':   _safe(row.get('open')),
            'high':   _safe(row.get('high')),
            'low':    _safe(row.get('low')),
            'volume': _safe(row.get('volume')),
            'signal': sig,
            'signal_label': sig_label,
            'rsi':    _safe(rsi.get(dt)),
            'macd':   _safe(macd.get(dt)),
            'macd_signal': _safe(macd_sig.get(dt)),
            'stoch_k': _safe(stoch_k.get(dt)),
            'stoch_d': _safe(stoch_d.get(dt)),
            'ma5':    _safe(ma5.get(dt)),
            'ma20':   _safe(ma20.get(dt)),
            'ma60':   _safe(ma60.get(dt)),
            'ma5_20_ratio':    _safe(ma5.get(dt) / ma20.get(dt)) if ma20.get(dt) else None,
            'ma20_60_ratio':   _safe(ma20.get(dt) / ma60.get(dt)) if ma60.get(dt) else None,
            'close_ma60_ratio':_safe(row.get('close') / ma60.get(dt)) if ma60.get(dt) else None,
            'confidence': None,
            'conditions_met': [],
            'conditions_not_met': [],
            'feature_importance': [],
            'predicted_at': predicted_at,
            'uploaded_at': datetime.now(timezone.utc),
        }

        result = col.update_one(
            {'stock_name': name, 'predicted_at': predicted_at},
            {'$set': doc},
            upsert=True,
        )
        if result.upserted_id or result.modified_count:
            upserted += 1

    return upserted


def run(from_date: str, to_date: str):
    import openpyxl
    col = _get_col()
    col.create_index([("stock_name", ASCENDING), ("predicted_at", ASCENDING)])

    # 종목 목록
    df_list = pd.read_excel(KOSPI_LIST)
    df_list['종목코드'] = df_list['종목코드'].astype(str).str.zfill(6)
    df_list['티커'] = df_list['종목코드'] + '.KS'

    total = 0
    n = len(df_list)
    for i, row in df_list.iterrows():
        ticker = row['티커']
        name   = row['종목명']
        cnt = process_ticker(ticker, name, from_date, to_date, col)
        total += cnt
        if (i + 1) % 20 == 0 or (i + 1) == n:
            logger.info(f"진행 {i+1}/{n} | 누적 upsert {total}건")

    logger.info(f"완료: 총 {total}건 upsert ({from_date} ~ {to_date})")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='특정 날짜 (예: 2026-06-20)')
    parser.add_argument('--from', dest='from_date', help='시작 날짜')
    args = parser.parse_args()

    today = datetime.now().strftime('%Y-%m-%d')

    if args.from_date:
        run(args.from_date, today)
    elif args.date:
        run(args.date, args.date)
    else:
        run(today, today)
