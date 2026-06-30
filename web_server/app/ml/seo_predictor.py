"""
app/ml/seo_predictor.py

LightGBM + XGBoost 앙상블 예측기 (seo-model-v1, seo-model-v2 공용).

1. run_full_seo_prediction  : engineered CSV 전체 기간 예측 -> total_trading_signals upsert
2. run_daily_seo_prediction : 매일 최신 데이터 예측 -> upsert (CSV 종목 전체 + KOSPI_STOCKS 보강)

종목명은 KRX 공식 목록 + ju-model-v2 매핑을 자동으로 캐싱하여 항상 한글로 채워짐.
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
        "csv_encoding": "utf-8-sig",
    },
    "seo-model-v2": {
        "model_dir": "/app/models/seo-model-v2",
        "csv_dir": "/app/collect_data/seojin",
        "csv_encoding": "utf-8-sig",
    },
}

_name_map_cache: dict = {}


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
        lgb_reg = None
        reg_path = os.path.join(model_dir, "lgb_regressor.pkl")
        if os.path.exists(reg_path):
            lgb_reg = joblib.load(reg_path)
        return lgb, xgb, features, label_map, lgb_reg
    except Exception as e:
        logger.error(f"[seo_predictor:{model_id}] 모델 로드 실패: {e}")
        return None


async def _get_name_map(db: AsyncIOMotorDatabase) -> dict:
    """종목코드 -> 한글 종목명 매핑. 프로세스 생존 동안 캐싱."""
    global _name_map_cache
    if _name_map_cache:
        return _name_map_cache

    name_map: dict = {}

    # 1. ju-model-v2에서 한글 종목명 가져오기 (가장 신뢰도 높음)
    try:
        col = db.total_trading_signals
        pipeline = [
            {"$match": {"model_id": "ju-model-v2"}},
            {"$group": {"_id": "$stock_code", "stock_name": {"$first": "$stock_name"}}},
        ]
        async for doc in col.aggregate(pipeline):
            if doc.get("stock_name") and doc["_id"]:
                name_map[doc["_id"]] = doc["stock_name"]
    except Exception as e:
        logger.warning(f"[seo_predictor] ju-model-v2 종목명 매핑 실패: {e}")

    # 2. KRX 공식 종목 목록으로 보강
    try:
        import requests
        import io
        url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
        res = requests.get(url, params={"method": "download", "searchType": "13"},
                           headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        res.encoding = "euc-kr"
        df = pd.read_html(io.StringIO(res.text))[0]
        df["종목코드"] = df["종목코드"].astype(str).str.zfill(6)
        for code, name in zip(df["종목코드"], df["회사명"]):
            if code not in name_map:
                name_map[code] = name
    except Exception as e:
        logger.warning(f"[seo_predictor] KRX 종목명 매핑 실패: {e}")

    _name_map_cache = name_map
    logger.info(f"[seo_predictor] 종목명 매핑 캐시 로드: {len(name_map)}개")
    return name_map


def _safe(v):
    try:
        f = float(v)
        return None if f != f else round(f, 4)
    except Exception:
        return None


def _predict_signal(lgb, xgb, features, label_map, row: pd.Series) -> tuple:
    """LGB + XGB 소프트 보팅으로 최종 신호 결정. (signal, pred_score) 반환.
    pred_score는 원본 시뮬레이션(simulation_rev1.py)과 동일하게 레이블 1(매수/급등) 클래스의 확률값.
    """
    import warnings
    idx_to_label = label_map.get("idx_to_label", {})
    label_to_idx = label_map.get("label_to_idx", {})
    X = pd.DataFrame([row[features].fillna(0).values], columns=features)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lgb_prob = lgb.predict_proba(X)[0]
        xgb_prob = xgb.predict_proba(X)[0]
    avg_prob = (lgb_prob + xgb_prob) / 2
    pred_idx = int(np.argmax(avg_prob))
    pred_label = idx_to_label.get(pred_idx, 2)

    buy_idx = label_to_idx.get(1, 1)
    pred_score = float(avg_prob[buy_idx]) if buy_idx < len(avg_prob) else 0.0

    return SEO_SIGNAL_MAP.get(pred_label, "관망"), round(pred_score, 4)


def _predict_reg_score(lgb_reg, features, row: pd.Series):
    """lgb_regressor 단독 예측값. 원본 simulation_rev1.py의 regressor 분기(model.predict(X))와 동일."""
    if lgb_reg is None:
        return None
    import warnings
    X = pd.DataFrame([row[features].fillna(0).values], columns=features)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        val = lgb_reg.predict(X)[0]
    return round(float(val), 6)


def _build_ohlcv_doc(row: pd.Series, stock_code: str, stock_name: str,
                     model_id: str, signal: str, pred_score: float, reg_score, predicted_at: datetime) -> dict:
    close = _safe(row.get("close_pric") or row.get("close"))
    open_ = _safe(row.get("open_pric") or row.get("open") or row.get("mkp"))
    high  = _safe(row.get("high_pric") or row.get("high") or row.get("hipr"))
    low   = _safe(row.get("low_pric")  or row.get("low")  or row.get("lopr"))
    vp = row.get("above_max_volume_profile")
    target = row.get("target")
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "model_id": model_id,
        "signal": signal,
        "pred_score": round(float(pred_score), 4) if pred_score is not None else None,
        "reg_score": round(float(reg_score), 6) if reg_score is not None else None,
        "above_max_volume_profile": int(vp) if vp is not None and not pd.isna(vp) else None,
        "target": int(target) if target is not None and not pd.isna(target) else None,
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

    lgb, xgb, features, label_map, lgb_reg = models
    csv_dir, csv_encoding = _get_csv_config(model_id)
    years = [2021, 2022, 2023, 2024, 2025, 2026]
    col = db.total_trading_signals
    await col.create_index([
        ("stock_code", ASCENDING),
        ("predicted_at", ASCENDING),
        ("model_id", ASCENDING)
    ])

    name_map = await _get_name_map(db)
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
            csv_name = str(row.get("itmsNm", "")).strip()
            stock_name = csv_name if (csv_name and csv_name != stock_code) else name_map.get(stock_code, stock_code)

            signal, pred_score = _predict_signal(lgb, xgb, features, label_map, row)
            reg_score = _predict_reg_score(lgb_reg, features, row)
            doc = _build_ohlcv_doc(row, stock_code, stock_name, model_id, signal, pred_score, reg_score, predicted_at)

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
    대상 종목: total_trading_signals에 이미 존재하는 해당 model_id의 전체 종목코드
    (CSV로 한 번 전체 예측을 돌린 뒤에는 그 종목 전체가 daily 갱신 대상이 됨)
    """
    models = _load_seo_model(model_id)
    if models is None:
        logger.error(f"[seo_predictor:{model_id}] 모델 없음 - daily 예측 중단")
        return

    lgb, xgb, features, label_map, lgb_reg = models

    from app.ml.trainer import KOSPI_STOCKS, _fetch_market_data, _build_features

    today = target_date or datetime.now().strftime("%Y-%m-%d")
    buf_start = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=120)).strftime("%Y-%m-%d")
    end_dt = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    col = db.total_trading_signals
    name_map = await _get_name_map(db)

    # 대상 종목: 기존에 이 모델로 예측된 적 있는 전체 종목 코드 (CSV 기반 풀 종목 커버)
    pipeline = [
        {"$match": {"model_id": model_id}},
        {"$group": {"_id": "$stock_code", "stock_name": {"$first": "$stock_name"}}},
    ]
    target_stocks = {}
    async for doc in col.aggregate(pipeline):
        code = doc["_id"]
        if code and code.isdigit() and len(code) == 6:
            target_stocks[code] = doc.get("stock_name") or name_map.get(code, code)

    # KOSPI_STOCKS도 보강 (ticker가 .KS인 경우 코드만 추출)
    for ticker, name, code in KOSPI_STOCKS:
        if code not in target_stocks:
            target_stocks[code] = name

    if not target_stocks:
        logger.warning(f"[seo_predictor:{model_id} daily] 대상 종목 없음 - 먼저 run_full_seo_prediction 필요")
        return

    market_map = _fetch_market_data(buf_start, end_dt)
    total = 0

    import asyncio
    loop = asyncio.get_event_loop()

    for code, name in target_stocks.items():
        ticker = f"{code}.KS"
        try:
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
                signal, pred_score = _predict_signal(lgb, xgb, features, label_map, feat_series)
                reg_score = _predict_reg_score(lgb_reg, features, feat_series)

                predicted_at = datetime(dt.year, dt.month, dt.day)
                doc = {
                    "stock_code": code, "stock_name": name,
                    "model_id": model_id, "signal": signal, "pred_score": pred_score, "reg_score": reg_score,
                    "above_max_volume_profile": None, "target": None,
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

    logger.info(f"[seo_predictor:{model_id} daily] 완료: {total}건 / 대상 {len(target_stocks)}개 종목 ({today})")


# 하위 호환성 유지용 래퍼
async def run_full_prediction(db: AsyncIOMotorDatabase):
    await run_full_seo_prediction(db, model_id="seo-model-v1")
