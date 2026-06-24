"""
app/ml/predictor.py

저장된 XGBoost 모델로 예측 + 성능 기록
- 예측 결과를 total_trading_signals에 upsert
- 실제 결과(N일 후 수익률)는 나중에 평가하여 model_predictions에 업데이트
"""
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING

from app.ml.trainer import FEATURE_COLS, LABEL_MAP, MODEL_PATH, KOSPI_STOCKS, _fetch_market_data, _build_features

logger = logging.getLogger(__name__)

HOLD_DAYS = 5  # 예측 평가 기준: N일 후 수익률


def _safe(v):
    try:
        f = float(v)
        return None if f != f else round(f, 4)
    except Exception:
        return None


async def run_daily_prediction(db: AsyncIOMotorDatabase, target_date: str = None):
    """매일 장 마감 후 전 종목 예측 + DB 저장"""
    from app.ml.trainer import load_model
    import asyncio

    model = load_model()
    if model is None:
        logger.warning("모델 없음. 학습 먼저 실행 필요")
        from app.ml.trainer import train_model
        await train_model(db, triggered_by="auto_init")
        model = load_model()

    today = target_date or datetime.now().strftime('%Y-%m-%d')
    logger.info(f"[predictor] 예측 시작: {today}")

    col_signals = db.total_trading_signals
    col_preds = db.model_predictions
    await col_signals.create_index([("stock_name", ASCENDING), ("predicted_at", ASCENDING)])
    await col_preds.create_index([("stock_name", ASCENDING), ("predicted_at", ASCENDING)])

    buf_start = (datetime.strptime(today, '%Y-%m-%d') - timedelta(days=120)).strftime('%Y-%m-%d')
    end_dt = (datetime.strptime(today, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    market_map = _fetch_market_data(buf_start, end_dt)

    total = 0
    for ticker, name, code in KOSPI_STOCKS:
        try:
            raw = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda t=ticker: yf.download(t, start=buf_start, end=end_dt,
                                              interval='1d', progress=False, auto_adjust=True)
            )
            if raw.empty:
                continue

            df = _build_features(raw, market_map, name)
            today_rows = df[df.index.strftime('%Y-%m-%d') == today]
            if today_rows.empty:
                continue

            for dt, row in today_rows.iterrows():
                feat = row[FEATURE_COLS]
                if feat.isna().any():
                    continue

                pred_label = int(model.predict(pd.DataFrame([feat]))[0])
                signal = LABEL_MAP.get(pred_label, '관망')
                predicted_at = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
                close_price = _safe(row.get('close'))

                # total_trading_signals upsert
                doc = {
                    'stock_code': code, 'stock_name': name,
                    'close': close_price, 'open': _safe(row.get('open')),
                    'high': _safe(row.get('high')), 'low': _safe(row.get('low')),
                    'volume': _safe(row.get('volume')),
                    'signal': signal, 'signal_label': pred_label,
                    'macd': _safe(row.get('macd')),
                    'stoch_k': _safe(row.get('stoch_k')), 'stoch_d': _safe(row.get('stoch_d')),
                    'ma5': _safe(row.get('ma5')), 'ma20': _safe(row.get('ma20')), 'ma60': _safe(row.get('ma60')),
                    'ma5_20_ratio': _safe(row.get('ma5_20_ratio')),
                    'ma20_60_ratio': _safe(row.get('ma20_60_ratio')),
                    'close_ma60_ratio': _safe(row.get('close_ma60_ratio')),
                    'vix_value': _safe(row.get('vix_value')),
                    'confidence': None, 'conditions_met': [], 'conditions_not_met': [],
                    'feature_importance': [],
                    'predicted_at': predicted_at,
                    'uploaded_at': datetime.now(timezone.utc),
                }
                await col_signals.update_one(
                    {'stock_name': name, 'predicted_at': predicted_at},
                    {'$set': doc}, upsert=True
                )

                # model_predictions: 성능 평가용 별도 저장
                # actual_return_pct는 N일 후 evaluate_predictions()에서 채움
                pred_doc = {
                    'stock_code': code, 'stock_name': name,
                    'signal': signal, 'signal_label': pred_label,
                    'close_at_prediction': close_price,
                    'predicted_at': predicted_at,
                    'evaluate_at': datetime(
                        (datetime.strptime(today, '%Y-%m-%d') + timedelta(days=HOLD_DAYS)).year,
                        (datetime.strptime(today, '%Y-%m-%d') + timedelta(days=HOLD_DAYS)).month,
                        (datetime.strptime(today, '%Y-%m-%d') + timedelta(days=HOLD_DAYS)).day,
                        tzinfo=timezone.utc
                    ),
                    'actual_return_pct': None,   # 나중에 채움
                    'is_correct': None,           # 나중에 채움
                    'evaluated': False,
                }
                await col_preds.update_one(
                    {'stock_name': name, 'predicted_at': predicted_at},
                    {'$set': pred_doc}, upsert=True
                )
                total += 1

        except Exception as e:
            logger.error(f"{name} 예측 실패: {e}")

    logger.info(f"[predictor] 완료: {total}건 저장 ({today})")


async def evaluate_predictions(db: AsyncIOMotorDatabase):
    """
    evaluate_at 날짜가 지난 미평가 예측건에 대해 실제 수익률 계산
    - 매수: N일 후 종가가 올랐으면 correct
    - 매도: N일 후 종가가 내렸으면 correct
    - 관망: 변동 없으면 correct (±1% 이내)
    """
    import asyncio
    now = datetime.now(timezone.utc)
    col = db.model_predictions

    # 평가 기한 지났고 아직 미평가된 것
    cursor = col.find({
        'evaluated': False,
        'evaluate_at': {'$lte': now},
        'close_at_prediction': {'$ne': None}
    }).limit(200)
    docs = [doc async for doc in cursor]
    if not docs:
        return

    logger.info(f"[evaluator] 평가 대상: {len(docs)}건")
    updated = 0

    # 종목+날짜 단위로 묶어서 yfinance 호출 최소화
    from collections import defaultdict
    groups = defaultdict(list)
    for doc in docs:
        code = doc.get('stock_code', '')
        if not code or not code.isdigit():
            sig = await db.total_trading_signals.find_one({'stock_name': doc.get('stock_name', '')}, {'stock_code': 1})
            code = sig.get('stock_code', '') if sig else ''
        if not code:
            continue
        eval_str = doc['evaluate_at'].strftime('%Y-%m-%d')
        groups[(code, eval_str)].append(doc)

    for (code, eval_str), group_docs in groups.items():
        ticker = code + '.KS'
        end_str = (datetime.strptime(eval_str, '%Y-%m-%d') + timedelta(days=3)).strftime('%Y-%m-%d')
        try:
            raw = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda t=ticker, s=eval_str, e=end_str: yf.download(
                    t, start=s, end=e, interval='1d', progress=False, auto_adjust=True
                )
            )
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.droplevel(1)
            raw.columns = [c.lower() for c in raw.columns]
            future_close = float(raw['close'].iloc[0])

            for doc in group_docs:
                close_at_pred = doc['close_at_prediction']
                signal = doc['signal']
                ret_pct = round((future_close - close_at_pred) / close_at_pred * 100, 2)
                if signal == '매수':
                    is_correct = ret_pct > 0
                elif signal == '매도':
                    is_correct = ret_pct < 0
                else:
                    is_correct = abs(ret_pct) <= 1.0
                await col.update_one(
                    {'_id': doc['_id']},
                    {'$set': {
                        'actual_return_pct': ret_pct,
                        'future_close': future_close,
                        'is_correct': is_correct,
                        'evaluated': True,
                        'evaluated_at': now,
                    }}
                )
                updated += 1
        except Exception as e:
            logger.warning(f"{ticker} 평가 실패: {e}")

    logger.info(f"[evaluator] 평가 완료: {updated}건")
