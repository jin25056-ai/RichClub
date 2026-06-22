"""
total_trading_signals.csv → MongoDB 업로드 스크립트

사용법:
  python upload_signals.py                    # 기본 CSV 경로 사용
  python upload_signals.py --csv /path/to/file.csv  # CSV 경로 직접 지정
  python upload_signals.py --replace          # 기존 컬렉션 전체 교체
"""
import os
import sys
import argparse
import logging
from datetime import datetime, timezone

import pandas as pd
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

DEFAULT_CSV = os.path.join(os.path.dirname(__file__), 'total_trading_signals.csv')

SIGNAL_TO_INT = {"매도": 0, "매수": 1, "관망": 2}


def load_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    logger.info(f"CSV 로드 완료: {len(df)}행, 컬럼={list(df.columns)}")
    return df


def preprocess(df: pd.DataFrame) -> list:
    """DataFrame → MongoDB 도큐먼트 리스트 변환"""
    docs = []

    # 컬럼명 정리
    col_map = {
        '날짜': 'date',
        '종목명': 'stock_name',
        '종가': 'close',
        '시그널': 'signal',
    }
    df = df.rename(columns=col_map)

    for _, row in df.iterrows():
        signal_str = str(row.get('signal', '관망')).strip()
        signal_label = SIGNAL_TO_INT.get(signal_str, 2)

        # 종목코드가 없으면 종목명으로 대체 (추후 종목코드 컬럼 추가 시 수정)
        stock_code = str(row.get('stock_code', row.get('종목코드', row.get('stock_name', '')))).strip()

        doc = {
            'stock_code': stock_code,
            'stock_name': str(row.get('stock_name', '')).strip(),
            'close': _safe_float(row.get('close')),
            'signal': signal_str,
            'signal_label': signal_label,
            'open': _safe_float(row.get('open')),
            'high': _safe_float(row.get('high')),
            'low': _safe_float(row.get('low')),
            'volume': _safe_float(row.get('volume')),
            # 기술적 지표
            'rsi': _safe_float(row.get('rsi')),
            'macd': _safe_float(row.get('macd')),
            'stoch_k': _safe_float(row.get('stoch_k')),
            'stoch_d': _safe_float(row.get('stoch_d')),
            'obv': _safe_float(row.get('obv')),
            'ma5_20_ratio': _safe_float(row.get('ma5_20_ratio')),
            'ma20_60_ratio': _safe_float(row.get('ma20_60_ratio')),
            'close_ma60_ratio': _safe_float(row.get('close_ma60_ratio')),
            'macd_change': _safe_float(row.get('macd_change')),
            'stoch_k_change': _safe_float(row.get('stoch_k_change')),
            'sp500_ma_ratio': _safe_float(row.get('sp500_ma_ratio')),
            'vix_value': _safe_float(row.get('vix_value')),
            'sp500': _safe_float(row.get('sp500')),
            'vix': _safe_float(row.get('vix')),
            # 신뢰도: target 컬럼이 있으면 활용 (예측 확률은 추후 모델에서 직접 저장)
            'confidence': None,
            # 충족/미충족 조건 (추후 retrain_pipeline에서 채움)
            'conditions_met': [],
            'conditions_not_met': [],
            'feature_importance': [],
            'predicted_at': _parse_date(row.get('date')),
            'uploaded_at': datetime.now(timezone.utc),
        }
        docs.append(doc)

    logger.info(f"전처리 완료: {len(docs)}건")
    return docs


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


def upload_to_mongo(docs: list, replace: bool = False):
    """MongoDB total_trading_signals 컬렉션에 업로드"""
    load_dotenv()
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client[os.getenv("MONGODB_DB", os.getenv("DB_NAME", "richclub"))]
    col = db["total_trading_signals"]

    if replace:
        col.drop()
        logger.info("기존 컬렉션 삭제 완료")

    if docs:
        result = col.insert_many(docs)
        logger.info(f"업로드 완료: {len(result.inserted_ids)}건 → total_trading_signals")

    # 인덱스 생성
    col.create_index([("stock_code", ASCENDING), ("predicted_at", ASCENDING)])
    col.create_index([("signal", ASCENDING)])
    col.create_index([("predicted_at", ASCENDING)])
    logger.info("인덱스 생성 완료")


def run(csv_path: str = DEFAULT_CSV, replace: bool = False):
    logger.info(f"CSV 경로: {csv_path}")
    df = load_csv(csv_path)
    docs = preprocess(df)
    upload_to_mongo(docs, replace=replace)
    logger.info("전체 업로드 완료")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', default=DEFAULT_CSV, help='CSV 파일 경로')
    parser.add_argument('--replace', action='store_true', help='기존 컬렉션 전체 교체')
    args = parser.parse_args()
    run(csv_path=args.csv, replace=args.replace)
