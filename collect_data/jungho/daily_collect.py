"""
daily_collect.py - 로컬에서 수동 실행용 (서버는 daily_collector.py 자동 실행)

실행:
  python daily_collect.py                    # 오늘
  python daily_collect.py --from 2026-06-18  # 특정 날짜부터
  python daily_collect.py --date 2026-06-20  # 특정 날짜
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

BASE_DIR = os.path.dirname(__file__)
MODEL_PATH = os.path.join(BASE_DIR, 'xgb_model.json')
KOSPI_LIST = os.path.join(BASE_DIR, 'kospi_list.xlsx')

FEATURE_COLS = [
    'ma5_20_ratio', 'ma20_60_ratio', 'close_ma60_ratio',
    'vol_change', 'macd', 'stoch_k', 'stoch_d', 'obv',
    'macd_change', 'stoch_k_change', 'sp500_ma_ratio', 'vix_value'
]
LABEL_MAP = {0: '매도', 1: '매수', 2: '관망'}


def _load_model():
    from xgboost import XGBClassifier
    model = XGBClassifier()
    if not os.path.exists(MODEL_PATH):
        logger.warning("모델 파일 없음. 학습 시작...")
        from train_and_save_model import train_and_save
        train_and_save()
    model.load_model(MODEL_PATH)
    logger.info(f"모델 로드: {MODEL_PATH}")
    return model


def _get_col():
    load_dotenv()
    uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or ""
    db_name = os.getenv("MONGODB_DB") or os.getenv("DB_NAME") or "richclub"
    return MongoClient(uri)[db_name]["total_trading_signals"]


def _load_kospi():
    df = pd.read_excel(KOSPI_LIST)
    df['종목코드'] = df['종목코드'].astype(str).str.zfill(6)
    df['티커'] = df['종목코드'] + '.KS'
    return df[['티커', '종목명', '종목코드']].to_dict('records')


def _fetch_market(start, end):
    try:
        mkt = yf.download(["^GSPC", "^VIX"], start=start, end=end, interval="1d", progress=False)
        if mkt.empty:
            return {}
        sp500 = mkt[('Close', '^GSPC')] if isinstance(mkt.columns, pd.MultiIndex) else mkt['Close']
        vix = mkt[('Close', '^VIX')] if isinstance(mkt.columns, pd.MultiIndex) else mkt['Close']
        return {pd.Timestamp(k).strftime('%Y-%m-%d'): {'sp500': float(sp500.get(k, np.nan)), 'vix': float(vix.get(k, np.nan))} for k in sp500.index}
    except Exception as e:
        logger.warning(f"시장 데이터 실패: {e}")
        return {}


def _safe(v):
    try:
        f = float(v)
        return None if f != f else round(f, 4)
    except Exception:
        return None


def _build_features(raw, market_map):
    df = raw.copy()
    df.columns = [c.lower() for c in df.columns]
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df = df.rename(columns={'adj close': 'close'})
    df.index = pd.to_datetime(df.index)
    df = df.dropna(subset=['close'])

    close = df['close']
    df['ma5'] = close.rolling(5).mean()
    df['ma20'] = close.rolling(20).mean()
    df['ma60'] = close.rolling(60).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    low_min = df['low'].rolling(12).min()
    high_max = df['high'].rolling(12).max()
    fast_k = 100 * ((close - low_min) / (high_max - low_min).replace(0, np.nan))
    df['stoch_k'] = fast_k.rolling(3).mean()
    df['stoch_d'] = df['stoch_k'].rolling(5).mean()
    df['obv'] = (np.sign(close.diff()) * df['volume']).fillna(0).cumsum()

    sp500_s = pd.Series({pd.Timestamp(k): v['sp500'] for k, v in market_map.items()})
    vix_s = pd.Series({pd.Timestamp(k): v['vix'] for k, v in market_map.items()})
    df['sp500'] = sp500_s.reindex(df.index, method='ffill')
    df['vix'] = vix_s.reindex(df.index, method='ffill')
    df['sp500_ma20'] = df['sp500'].rolling(20).mean()
    df['vix_change'] = df['vix'].pct_change()
    df['vix_value'] = df['vix']

    df['ma5_20_ratio'] = df['ma5'] / df['ma20']
    df['ma20_60_ratio'] = df['ma20'] / df['ma60']
    df['close_ma60_ratio'] = close / df['ma60']
    df['vol_change'] = df['volume'].pct_change()
    df['macd_change'] = df['macd'].diff()
    df['stoch_k_change'] = df['stoch_k'].diff()
    df['sp500_ma_ratio'] = df['sp500'] / df['sp500_ma20']
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df


def run(from_date: str, to_date: str):
    model = _load_model()
    col = _get_col()
    col.create_index([("stock_name", ASCENDING), ("predicted_at", ASCENDING)])
    stocks = _load_kospi()

    buf_start = (datetime.strptime(from_date, '%Y-%m-%d') - timedelta(days=120)).strftime('%Y-%m-%d')
    end_dt = (datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    market_map = _fetch_market(buf_start, end_dt)

    total = 0
    for i, s in enumerate(stocks):
        try:
            raw = yf.download(s['티커'], start=buf_start, end=end_dt, interval='1d', progress=False, auto_adjust=True)
            if raw.empty:
                continue
            df = _build_features(raw, market_map)
            mask = (df.index.strftime('%Y-%m-%d') >= from_date) & (df.index.strftime('%Y-%m-%d') <= to_date)
            for dt, row in df[mask].iterrows():
                feat = row[FEATURE_COLS]
                if feat.isna().any():
                    continue
                pred = model.predict(pd.DataFrame([feat]))[0]
                signal = LABEL_MAP.get(int(pred), '관망')
                predicted_at = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
                doc = {
                    'stock_code': s['종목코드'], 'stock_name': s['종목명'],
                    'close': _safe(row.get('close')), 'open': _safe(row.get('open')),
                    'high': _safe(row.get('high')), 'low': _safe(row.get('low')),
                    'volume': _safe(row.get('volume')), 'signal': signal,
                    'signal_label': int(pred), 'macd': _safe(row.get('macd')),
                    'stoch_k': _safe(row.get('stoch_k')), 'stoch_d': _safe(row.get('stoch_d')),
                    'ma5': _safe(row.get('ma5')), 'ma20': _safe(row.get('ma20')), 'ma60': _safe(row.get('ma60')),
                    'ma5_20_ratio': _safe(row.get('ma5_20_ratio')),
                    'ma20_60_ratio': _safe(row.get('ma20_60_ratio')),
                    'close_ma60_ratio': _safe(row.get('close_ma60_ratio')),
                    'vix_value': _safe(row.get('vix_value')),
                    'confidence': None, 'conditions_met': [], 'conditions_not_met': [],
                    'feature_importance': [], 'predicted_at': predicted_at,
                    'uploaded_at': datetime.now(timezone.utc),
                }
                result = col.update_one(
                    {'stock_name': s['종목명'], 'predicted_at': predicted_at},
                    {'$set': doc}, upsert=True
                )
                if result.upserted_id or result.modified_count:
                    total += 1
        except Exception as e:
            logger.error(f"{s['종목명']} 실패: {e}")
        if (i + 1) % 20 == 0 or (i + 1) == len(stocks):
            logger.info(f"진행 {i+1}/{len(stocks)} | upsert {total}건")

    logger.info(f"완료: {total}건 ({from_date} ~ {to_date})")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='특정 날짜 (YYYY-MM-DD)')
    parser.add_argument('--from', dest='from_date', help='시작 날짜')
    args = parser.parse_args()
    today = datetime.now().strftime('%Y-%m-%d')
    if args.from_date:
        run(args.from_date, today)
    elif args.date:
        run(args.date, args.date)
    else:
        run(today, today)
