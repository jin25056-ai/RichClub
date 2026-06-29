"""
app/ml/seo_predictor.py

LightGBM + XGBoost 앙상블 예측기 (seo-model-v1, seo-model-v2 공용).

1. run_full_seo_prediction  : engineered CSV 전체 기간 예측 -> total_trading_signals upsert
2. run_daily_seo_prediction : 매일 최신 데이터 예측 -> upsert
"""
import logging
import os
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd
import yfinance as yf
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, UpdateOne

logger = logging.getLogger(__name__)

# 레이블 매핑 (0=매도, 1=급등/매수, 2=관망, 3=침체)
SEO_SIGNAL_MAP = {0: "매도", 1: "매수", 2: "관망", 3: "관망"}

# 모델별 설정
MODEL_CONFIGS = {
    "seo-model-v1": {
        "model_dir": "/app/models/seo-model-v1",
        "csv_dir": "/app/collect_data/seojin",
        "csv_encoding": "cp949",
    },
    "seo-model-v2": {
        "model_dir": "/app/models/seo-model-v2",
        "csv_dir": "/app/collect_data/seojin",
        "csv_encoding": "utf-8-sig",
    },
}


def _get_model_dir(model_id: str) -> str:
    return MODEL_CONFIGS.get(model_id, {}).get("model_dir", f"/app/models/{model_id}")


def _get_csv_config(model_id: str) -> tuple:
    cfg = MODEL_CONFIGS.get(model_id, {})
    return cfg.get("csv_dir", "/app/collect_data/seojin"), cfg.get("csv_encoding", "utf-8-sig")


def _load_seo_model(model_id: str):
    """pkl 파일 로드. 없으면 None 반환."""
    model_dir = _get_model_dir(model_id)
    try:
        lgb = joblib.load(os.path.join(model_dir, "lgb_classifier.pkl"))
        xgb = joblib.load(os.path.join(model_dir, "xgb_classifier.pkl"))
        features = joblib.load(os.path.join(model_dir, "model_features.pkl"))
        label_map = joblib.load(os.path.join(model_dir, "target_label_map.pkl"))
        return lgb, xgb, features, label_map
    except Exception as e:
        logger.error(f"[seo_predictor:{model_id}] 모델 로드 실패: {e}")
        return None


def _safe(v):
    try:
        f = float(v)
        return None if f != f else round(f, 4)
    except Exception:
        return None


def _predict_signal(lgb, xgb, features, label_map, row: pd.Series) -> str:
    """LGB + XGB 소프트 보팅으로 최종 신호 결정."""
    import warnings
    idx_to_label = label_map.get("idx_to_label", {})
    X = pd.DataFrame([row[features].fillna(0).values], columns=features)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lgb_prob = lgb.predict_proba(X)[0]
        xgb_prob = xgb.predict_proba(X)[0]
    avg_prob = (lgb_prob + xgb_prob) / 2
    pred_idx = int(np.argmax(avg_prob))
    pred_label = idx_to_label.get(pred_idx, 2)
    return SEO_SIGNAL_MAP.get(pred_label, "관망")


def _build_ohlcv_doc(row: pd.Series, stock_code: str, stock_name: str,
                     model_id: str, signal: str, predicted_at: datetime) -> dict:
    close = _safe(row.get("close_pric") or row.get("close"))
    open_ = _safe(row.get("open_pric") or row.get("open") or row.get("mkp"))
    high  = _safe(row.get("high_pric") or row.get("high") or row.get("hipr"))
    low   = _safe(row.get("low_pric")  or row.get("low")  or row.get("lopr"))
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "model_id": model_id,
        "signal": signal,
        "close": close,
        "open": open_,
        "high": high,
        "low": low,
        "ma5":  _safe(row.get("ma5")),
        "ma20": _safe(row.get("ma20")),
        "ma60": _safe(row.get("ma60")),
        "predicted_at": predicted_at,
        "uploaded_at": datetime.utcnow(),
        "ret_1d": None, "ret_5d": None, "ret_20d": None, "ret_60d": None,
    }


async def run_full_seo_prediction(db: AsyncIOMotorDatabase, model_id: str = "seo-model-v1"):
    """
    engineered CSV 전체 기간 예측 -> total_trading_signals upsert.
    이미 해당 날짜 + model_id 로 저장된 건은 건너뜀.
    """
    models = _load_seo_model(model_id)
    if models is None:
        logger.error(f"[seo_predictor:{model_id}] 모델 없음 - 전체 예측 중단")
        return

    lgb, xgb, features, label_map = models
    csv_dir, csv_encoding = _get_csv_config(model_id)
    years = [2021, 2022, 2023, 2024, 2025, 2026]
    col = db.total_trading_signals
    await col.create_index([
        ("stock_code", ASCENDING),
        ("predicted_at", ASCENDING),
        ("model_id", ASCENDING)
    ])

    total_inserted = 0

    for year in years:
        csv_path = os.path.join(csv_dir, f"engineered_stock_data_{year}.csv")
        if not os.path.exists(csv_path):
            logger.warning(f"[seo_predictor:{model_id}] CSV 없음: {csv_path}")
            continue

        logger.info(f"[seo_predictor:{model_id}] {year}년 CSV 로드 중...")
        try:
            df = pd.read_csv(csv_path, encoding=csv_encoding)
        except Exception as e:
            logger.error(f"[seo_predictor:{model_id}] CSV 로드 실패 ({year}): {e}")
            continue

        if "stk_cd" not in df.columns or "date" not in df.columns:
            logger.error(f"[seo_predictor:{model_id}] {year} CSV 컬럼 오류")
            continue

        for f in features:
            if f not in df.columns:
                df[f] = 0
        df[features] = df[features].apply(pd.to_numeric, errors="coerce").fillna(0)

        bulk_ops = []
        for _, row in df.iterrows():
            try:
                date_str = str(row["date"]).strip()
                # YYYYMMDD 또는 YYYY-MM-DD 둘 다 처리
                if "-" in date_str:
                    predicted_at = datetime.strptime(date_str, "%Y-%m-%d")
                else:
                    predicted_at = datetime.strptime(date_str, "%Y%m%d")
            except Exception:
                continue

            stock_code = str(int(row["stk_cd"])).zfill(6)
            stock_name = str(row.get("itmsNm", stock_code)).strip()

            signal = _predict_signal(lgb, xgb, features, label_map, row)
            doc = _build_ohlcv_doc(row, stock_code, stock_name, model_id, signal, predicted_at)

            bulk_ops.append(UpdateOne(
                {"stock_code": stock_code, "predicted_at": predicted_at, "model_id": model_id},
                {"$set": doc},
                upsert=True,
            ))

            if len(bulk_ops) >= 500:
                result = await col.bulk_write(bulk_ops, ordered=False)
                total_inserted += result.upserted_count + result.modified_count
                bulk_ops = []

        if bulk_ops:
            result = await col.bulk_write(bulk_ops, ordered=False)
            total_inserted += result.upserted_count + result.modified_count

        logger.info(f"[seo_predictor:{model_id}] {year}년 완료")

    logger.info(f"[seo_predictor:{model_id}] 전체 예측 완료: 총 {total_inserted}건 upsert")


async def run_daily_seo_prediction(db: AsyncIOMotorDatabase, model_id: str = "seo-model-v1", target_date: str = None):
    """
    매일 장 마감 후 yfinance 로 최신 데이터 수집 -> 예측 -> upsert.
    """
    models = _load_seo_model(model_id)
    if models is None:
        logger.error(f"[seo_predictor:{model_id}] 모델 없음 - daily 예측 중단")
        return

    lgb, xgb, features, label_map = models

    from app.ml.trainer import KOSPI_STOCKS, _fetch_market_data, _build_features, FEATURE_COLS

    today = target_date or datetime.now().strftime("%Y-%m-%d")
    buf_start = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=120)).strftime("%Y-%m-%d")
    end_dt = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    market_map = _fetch_market_data(buf_start, end_dt)
    col = db.total_trading_signals
    total = 0

    for ticker, name, code in KOSPI_STOCKS:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(
                None,
                lambda t=ticker: yf.download(t, start=buf_start, end=end_dt,
                                              interval="1d", progress=False, auto_adjust=True)
            )
            if raw is None or raw.empty:
                continue

            df = _build_features(raw, market_map, name)
            today_rows = df[df.index.strftime("%Y-%m-%d") == today]
            if today_rows.empty:
                continue

            for dt, row in today_rows.iterrows():
                feat_series = pd.Series({f: row.get(f, 0) for f in features}).fillna(0)
                signal = _predict_signal(lgb, xgb, features, label_map, feat_series)

                predicted_at = datetime(dt.year, dt.month, dt.day)
                doc = {
                    "stock_code": code, "stock_name": name,
                    "model_id": model_id, "signal": signal,
                    "close": _safe(row.get("close")), "open": _safe(row.get("open")),
                    "high": _safe(row.get("high")), "low": _safe(row.get("low")),
                    "volume": _safe(row.get("volume")),
                    "ma5": _safe(row.get("ma5")), "ma20": _safe(row.get("ma20")), "ma60": _safe(row.get("ma60")),
                    "predicted_at": predicted_at, "uploaded_at": datetime.utcnow(),
                    "ret_1d": None, "ret_5d": None, "ret_20d": None, "ret_60d": None,
                }
                await col.update_one(
                    {"stock_code": code, "predicted_at": predicted_at, "model_id": model_id},
                    {"$set": doc}, upsert=True
                )
                total += 1

        except Exception as e:
            logger.error(f"[seo_predictor:{model_id} daily] {name}({ticker}) 실패: {e}")

    logger.info(f"[seo_predictor:{model_id} daily] 완료: {total}건 ({today})")


# 하위 호환성 유지용 래퍼
async def run_full_prediction(db: AsyncIOMotorDatabase):
    await run_full_seo_prediction(db, model_id="seo-model-v1")
