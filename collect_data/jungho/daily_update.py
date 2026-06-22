"""
daily_update.py - 매일 장 마감 후 오늘 날짜 신호를 DB에 upsert

사용법:
  python daily_update.py                    # 오늘 날짜 데이터만 upsert
  python daily_update.py --date 2026-06-20  # 특정 날짜 upsert
  python daily_update.py --from 2026-06-18  # 특정 날짜부터 오늘까지 전체 upsert

Windows 작업 스케줄러 등록 예시 (매일 오후 4시 실행):
  schtasks /create /tn "RichClub Daily Update" /tr "C:\\Python\\python.exe C:\\...\\daily_update.py" /sc daily /st 16:00

실행 전 환경변수 설정:
  $env:MONGODB_URI="mongodb+srv://richclub_user:wBzJQpD2lcz1vMBE@datacluster0.5v6tfgd.mongodb.net"
  $env:MONGODB_DB="richclub"
"""
import os
import sys
import argparse
import logging
from datetime import datetime, timezone, timedelta

import pandas as pd
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

DEFAULT_CSV = os.path.join(os.path.dirname(__file__), 'total_trading_signals.csv')
SIGNAL_TO_INT = {"매도": 0, "매수": 1, "관망": 2}


def _get_mongo_uri() -> str:
    return os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or ""


def _get_db_name() -> str:
    return os.getenv("MONGODB_DB") or os.getenv("DB_NAME") or "richclub"


def _safe_float(val):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_date(val) -> datetime:
    if val is None:
        return datetime.now(timezone.utc)
    try:
        return pd.to_datetime(val).to_pydatetime().replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _row_to_doc(row) -> dict:
    signal_str = str(row.get('signal', row.get('시그널', '관망'))).strip()
    stock_name = str(row.get('stock_name', row.get('종목명', ''))).strip()
    stock_code = str(row.get('stock_code', row.get('종목코드', stock_name))).strip()

    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'close': _safe_float(row.get('close', row.get('종가'))),
        'signal': signal_str,
        'signal_label': SIGNAL_TO_INT.get(signal_str, 2),
        'open': _safe_float(row.get('open')),
        'high': _safe_float(row.get('high')),
        'low': _safe_float(row.get('low')),
        'volume': _safe_float(row.get('volume')),
        'rsi': _safe_float(row.get('rsi')),
        'macd': _safe_float(row.get('macd')),
        'stoch_k': _safe_float(row.get('stoch_k')),
        'stoch_d': _safe_float(row.get('stoch_d')),
        'ma5': _safe_float(row.get('ma5')),
        'ma20': _safe_float(row.get('ma20')),
        'ma60': _safe_float(row.get('ma60')),
        'ma5_20_ratio': _safe_float(row.get('ma5_20_ratio')),
        'ma20_60_ratio': _safe_float(row.get('ma20_60_ratio')),
        'close_ma60_ratio': _safe_float(row.get('close_ma60_ratio')),
        'vix_value': _safe_float(row.get('vix_value')),
        'confidence': None,
        'conditions_met': [],
        'conditions_not_met': [],
        'feature_importance': [],
        'predicted_at': _parse_date(row.get('date', row.get('날짜'))),
        'uploaded_at': datetime.now(timezone.utc),
    }


def upsert_by_date(csv_path: str, from_date: str, to_date: str):
    """지정 날짜 범위의 데이터를 CSV에서 읽어 DB에 upsert"""
    load_dotenv()

    logger.info(f"CSV 읽는 중: {csv_path}")
    df = pd.read_csv(csv_path, encoding='utf-8-sig')

    # 날짜 컬럼 찾기
    date_col = '날짜' if '날짜' in df.columns else 'date'
    if date_col not in df.columns:
        logger.error(f"날짜 컬럼을 찾을 수 없습니다. 컬럼: {list(df.columns)}")
        return

    # 컬럼명 통일
    if '날짜' in df.columns:
        df = df.rename(columns={'날짜': 'date', '종목명': 'stock_name', '종가': 'close', '시그널': 'signal'})

    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    filtered = df[(df['date'] >= from_date) & (df['date'] <= to_date)]

    if filtered.empty:
        logger.warning(f"{from_date} ~ {to_date} 범위의 데이터가 CSV에 없습니다.")
        return

    logger.info(f"대상 데이터: {len(filtered)}건 ({from_date} ~ {to_date})")

    uri = _get_mongo_uri()
    db_name = _get_db_name()
    client = MongoClient(uri)
    col = client[db_name]["total_trading_signals"]

    upserted = 0
    for _, row in filtered.iterrows():
        doc = _row_to_doc(row)
        # stock_name + predicted_at 기준으로 upsert (중복 방지)
        result = col.update_one(
            {
                'stock_name': doc['stock_name'],
                'predicted_at': doc['predicted_at'],
            },
            {'$set': doc},
            upsert=True,
        )
        if result.upserted_id or result.modified_count:
            upserted += 1

    logger.info(f"upsert 완료: {upserted}건")

    # 인덱스 확인
    col.create_index([("stock_code", ASCENDING), ("predicted_at", ASCENDING)])
    col.create_index([("stock_name", ASCENDING), ("predicted_at", ASCENDING)])


def run(csv_path: str, target_date: str = None, from_date: str = None):
    today = datetime.now().strftime('%Y-%m-%d')

    if from_date:
        # --from 지정: from_date ~ 오늘
        upsert_by_date(csv_path, from_date, today)
    elif target_date:
        # --date 지정: 해당 날짜만
        upsert_by_date(csv_path, target_date, target_date)
    else:
        # 기본: 오늘 날짜만
        upsert_by_date(csv_path, today, today)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RichClub 일별 신호 DB 업데이트')
    parser.add_argument('--csv', default=DEFAULT_CSV, help='CSV 파일 경로')
    parser.add_argument('--date', help='특정 날짜 (예: 2026-06-20)')
    parser.add_argument('--from', dest='from_date', help='시작 날짜 (예: 2026-06-18)')
    args = parser.parse_args()
    run(csv_path=args.csv, target_date=args.date, from_date=args.from_date)
