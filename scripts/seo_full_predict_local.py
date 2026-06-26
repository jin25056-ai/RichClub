"""
로컬 실행 스크립트: seo-model-v1 전체 기간 예측 -> MongoDB Atlas 직접 저장

실행:
    python scripts/seo_full_predict_local.py
"""
import os
import sys
import logging
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from pymongo import MongoClient, ASCENDING, UpdateOne

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "web_server", "app", "models", "seo-model-v1")
CSV_DIR   = os.path.join(BASE_DIR, "collect_data", "seojin")

MONGODB_URI = "mongodb+srv://richclub_user:wBzJQpD2lcz1vMBE@datacluster0.5v6tfgd.mongodb.net"
MONGODB_DB  = "richclub"
MODEL_ID    = "seo-model-v1"
YEARS       = [2021, 2022, 2023, 2024, 2025, 2026]

# seo-model 레이블: 0=매도, 1=매수, 2=관망, 3=침체→관망
SEO_SIGNAL_MAP = {0: "매도", 1: "매수", 2: "관망", 3: "관망"}


def _safe(v):
    try:
        f = float(v)
        return None if f != f else round(f, 4)
    except Exception:
        return None


def load_models():
    logger.info("모델 로드 중...")
    lgb      = joblib.load(os.path.join(MODEL_DIR, "lgb_classifier.pkl"))
    xgb      = joblib.load(os.path.join(MODEL_DIR, "xgb_classifier.pkl"))
    features = joblib.load(os.path.join(MODEL_DIR, "model_features.pkl"))
    label_map = joblib.load(os.path.join(MODEL_DIR, "target_label_map.pkl"))
    logger.info(f"모델 로드 완료 - 피처 수: {len(features)}")
    return lgb, xgb, features, label_map


def predict_signal(lgb, xgb, features, idx_to_label, row: pd.Series) -> str:
    X = row[features].fillna(0).values.reshape(1, -1)
    lgb_prob = lgb.predict_proba(X)[0]
    xgb_prob = xgb.predict_proba(X)[0]
    avg_prob = (lgb_prob + xgb_prob) / 2
    pred_idx = int(np.argmax(avg_prob))
    pred_label = idx_to_label.get(pred_idx, 2)
    return SEO_SIGNAL_MAP.get(pred_label, "관망")


def main():
    # 모델 로드
    lgb, xgb, features, label_map = load_models()
    idx_to_label = label_map.get("idx_to_label", {})

    # MongoDB 연결
    logger.info("MongoDB 연결 중...")
    client = MongoClient(MONGODB_URI)
    col = client[MONGODB_DB]["total_trading_signals"]
    col.create_index([("stock_code", ASCENDING), ("predicted_at", ASCENDING), ("model_id", ASCENDING)])
    logger.info("MongoDB 연결 완료")

    total_upserted = 0

    for year in YEARS:
        csv_path = os.path.join(CSV_DIR, f"engineered_stock_data_{year}.csv")
        if not os.path.exists(csv_path):
            logger.warning(f"CSV 없음: {csv_path}")
            continue

        logger.info(f"[{year}] CSV 로드 중... ({os.path.getsize(csv_path) // 1024 // 1024}MB)")
        df = pd.read_csv(csv_path, encoding="cp949")
        logger.info(f"[{year}] {len(df)}행 로드 완료")

        # 피처 없는 컬럼은 0으로
        for f in features:
            if f not in df.columns:
                df[f] = 0
        df[features] = df[features].apply(pd.to_numeric, errors="coerce").fillna(0)

        bulk_ops = []
        skipped = 0

        for _, row in df.iterrows():
            try:
                predicted_at = datetime.strptime(str(int(row["date"])), "%Y%m%d")
            except Exception:
                skipped += 1
                continue

            stock_code = str(int(row["stk_cd"])).zfill(6)
            stock_name = str(row.get("itmsNm", stock_code)).strip()

            signal = predict_signal(lgb, xgb, features, idx_to_label, row)

            doc = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "model_id": MODEL_ID,
                "signal": signal,
                "close": _safe(row.get("close_pric") or row.get("close")),
                "open":  _safe(row.get("open_pric")  or row.get("mkp")),
                "high":  _safe(row.get("high_pric")  or row.get("hipr")),
                "low":   _safe(row.get("low_pric")   or row.get("lopr")),
                "ma5":   _safe(row.get("ma5")),
                "ma20":  _safe(row.get("ma20")),
                "ma60":  _safe(row.get("ma60")),
                "predicted_at": predicted_at,
                "uploaded_at": datetime.utcnow(),
                "ret_1d": None, "ret_5d": None, "ret_20d": None, "ret_60d": None,
            }

            bulk_ops.append(UpdateOne(
                {"stock_code": stock_code, "predicted_at": predicted_at, "model_id": MODEL_ID},
                {"$set": doc},
                upsert=True,
            ))

            # 500건마다 flush
            if len(bulk_ops) >= 500:
                result = col.bulk_write(bulk_ops, ordered=False)
                total_upserted += result.upserted_count + result.modified_count
                bulk_ops = []

        # 나머지 flush
        if bulk_ops:
            result = col.bulk_write(bulk_ops, ordered=False)
            total_upserted += result.upserted_count + result.modified_count

        logger.info(f"[{year}] 완료 - 스킵: {skipped}건, 누적 저장: {total_upserted}건")

    logger.info(f"전체 완료 - 총 {total_upserted}건 저장")
    client.close()


if __name__ == "__main__":
    main()
