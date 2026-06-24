"""
app/ml/predictor.py

1. run_daily_prediction: 매일 장 마감 후 XGBoost 예측 → total_trading_signals upsert
2. calculate_returns: total_trading_signals 내에서 +1/5/20/60일 수익률 계산 후 업데이트
3. aggregate_monthly_performance: 월별 성능 집계 → model_performance_monthly 저장
4. check_and_retrain: 성능 나쁜 월 이후 자동 재학습
"""
import logging
from datetime import datetime, timezone, timedelta

import pandas as pd
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, UpdateOne

from app.ml.trainer import FEATURE_COLS, LABEL_MAP, KOSPI_STOCKS, _fetch_market_data, _build_features

logger = logging.getLogger(__name__)


def _safe(v):
    try:
        f = float(v)
        return None if f != f else round(f, 4)
    except Exception:
        return None


async def run_daily_prediction(db: AsyncIOMotorDatabase, target_date: str = None):
    """매일 장 마감 후 전 종목 XGBoost 예측 → total_trading_signals upsert"""
    import asyncio
    import yfinance as yf
    from app.ml.trainer import load_model

    model = load_model()
    if model is None:
        logger.warning("모델 없음. 학습 시작")
        from app.ml.trainer import train_model
        await train_model(db, triggered_by="auto_init")
        model = load_model()

    today = target_date or datetime.now().strftime('%Y-%m-%d')
    logger.info(f"[predictor] 예측 시작: {today}")

    col = db.total_trading_signals
    await col.create_index([("stock_name", ASCENDING), ("predicted_at", ASCENDING)])

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
                predicted_at = datetime(dt.year, dt.month, dt.day)

                doc = {
                    'stock_code': code, 'stock_name': name,
                    'close': _safe(row.get('close')), 'open': _safe(row.get('open')),
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
                    'predicted_at': predicted_at,
                    'uploaded_at': datetime.utcnow(),
                    # 수익률 필드 (나중에 calculate_returns가 채움)
                    'ret_1d': None, 'ret_5d': None, 'ret_20d': None, 'ret_60d': None,
                    'is_correct_5d': None,
                }
                await col.update_one(
                    {'stock_name': name, 'predicted_at': predicted_at},
                    {'$set': doc}, upsert=True
                )
                total += 1

        except Exception as e:
            logger.error(f"{name} 예측 실패: {e}")

    logger.info(f"[predictor] 완료: {total}건 ({today})")

    # 예측 후 수익률 계산 실행
    await calculate_returns(db)


async def calculate_returns(db: AsyncIOMotorDatabase):
    """
    total_trading_signals 내에서 종목별로
    +1일/+5일/+20일/+60일 후 close를 같은 컬렉션에서 찾아서 수익률 업데이트
    수익률이 없는 것들만 처리 (매일 돌려도 안전)
    """
    col = db.total_trading_signals

    # ret_5d가 없고 predicted_at이 충분히 과거인 것들 처리 (5일 이상 지난 것)
    cutoff = datetime.utcnow() - timedelta(days=5)
    cursor = col.find({
        'ret_5d': None,
        'close': {'$ne': None},
        'predicted_at': {'$lte': cutoff}
    }).limit(1000)
    docs = [doc async for doc in cursor]

    if not docs:
        logger.info("[returns] 계산할 데이터 없음")
        return

    logger.info(f"[returns] 수익률 계산 대상: {len(docs)}건")
    bulk_ops = []

    for doc in docs:
        name = doc.get('stock_name')
        base_close = doc.get('close')
        predicted_at = doc.get('predicted_at')
        signal = doc.get('signal', '관망')

        if not base_close or not predicted_at:
            continue

        # predicted_at을 naive datetime으로 통일
        if hasattr(predicted_at, 'tzinfo') and predicted_at.tzinfo:
            predicted_at = predicted_at.replace(tzinfo=None)

        ret = {}
        for days, key in [(1, 'ret_1d'), (5, 'ret_5d'), (20, 'ret_20d'), (60, 'ret_60d')]:
            target_dt = predicted_at + timedelta(days=days)
            # target_dt 이후 가장 가까운 거래일 데이터 조회 (최대 7일 이내)
            future = await col.find_one(
                {
                    'stock_name': name,
                    'predicted_at': {'$gte': target_dt, '$lte': target_dt + timedelta(days=7)},
                    'close': {'$ne': None}
                },
                sort=[('predicted_at', 1)],
                projection={'close': 1}
            )
            if future and future.get('close'):
                ret[key] = round((float(future['close']) - float(base_close)) / float(base_close) * 100, 2)
            else:
                ret[key] = None

        # 5일 수익률 기준 신호 적중 여부
        if ret.get('ret_5d') is not None:
            r = ret['ret_5d']
            if signal == '매수':
                is_correct = r > 0
            elif signal == '매도':
                is_correct = r < 0
            else:
                is_correct = abs(r) <= 1.0
            ret['is_correct_5d'] = is_correct

        bulk_ops.append(UpdateOne({'_id': doc['_id']}, {'$set': ret}))

    if bulk_ops:
        result = await col.bulk_write(bulk_ops, ordered=False)
        logger.info(f"[returns] 수익률 업데이트: {result.modified_count}건")


async def aggregate_monthly_performance(db: AsyncIOMotorDatabase):
    """
    total_trading_signals에서 월별 성능 집계 → model_performance_monthly 저장
    매월 1일 자동 실행
    """
    pipeline = [
        {'$match': {'ret_5d': {'$ne': None}, 'is_correct_5d': {'$ne': None}}},
        {'$group': {
            '_id': {
                'year': {'$year': '$predicted_at'},
                'month': {'$month': '$predicted_at'},
                'signal': '$signal',
            },
            'total': {'$sum': 1},
            'correct': {'$sum': {'$cond': ['$is_correct_5d', 1, 0]}},
            'avg_ret_5d': {'$avg': '$ret_5d'},
            'avg_ret_1d': {'$avg': '$ret_1d'},
            'avg_ret_20d': {'$avg': '$ret_20d'},
        }},
        {'$sort': {'_id.year': 1, '_id.month': 1, '_id.signal': 1}},
    ]
    col_monthly = db.model_performance_monthly
    results = [doc async for doc in db.total_trading_signals.aggregate(pipeline)]

    if not results:
        return

    bulk_ops = []
    for r in results:
        ym = r['_id']
        month_str = f"{ym['year']}-{ym['month']:02d}"
        total = r['total']
        correct = r['correct']
        bulk_ops.append(UpdateOne(
            {'month': month_str, 'signal': ym['signal']},
            {'$set': {
                'month': month_str,
                'year': ym['year'],
                'month_num': ym['month'],
                'signal': ym['signal'],
                'total': total,
                'correct': correct,
                'accuracy': round(correct / total * 100, 1) if total > 0 else 0,
                'avg_ret_5d': round(r.get('avg_ret_5d') or 0, 2),
                'avg_ret_1d': round(r.get('avg_ret_1d') or 0, 2),
                'avg_ret_20d': round(r.get('avg_ret_20d') or 0, 2),
                'updated_at': datetime.utcnow(),
            }},
            upsert=True
        ))

    await col_monthly.bulk_write(bulk_ops, ordered=False)
    logger.info(f"[monthly] 월별 성능 집계 완료: {len(results)}건")


async def check_and_retrain(db: AsyncIOMotorDatabase):
    """
    최근 2개월 매수 신호 정확도가 50% 미만이면 자동 재학습
    """
    two_months_ago = datetime.utcnow() - timedelta(days=60)
    pipeline = [
        {'$match': {
            'signal': '매수',
            'is_correct_5d': {'$ne': None},
            'predicted_at': {'$gte': two_months_ago}
        }},
        {'$group': {
            '_id': None,
            'total': {'$sum': 1},
            'correct': {'$sum': {'$cond': ['$is_correct_5d', 1, 0]}},
        }},
    ]
    results = [doc async for doc in db.total_trading_signals.aggregate(pipeline)]
    if not results or results[0]['total'] < 30:
        return

    acc = results[0]['correct'] / results[0]['total']
    logger.info(f"[check_retrain] 최근 2개월 매수 정확도: {acc:.1%} ({results[0]['correct']}/{results[0]['total']})")

    if acc < 0.50:
        logger.warning("[check_retrain] 정확도 50% 미만 → 자동 재학습")
        from app.ml.trainer import train_model
        await train_model(db, triggered_by="auto_drift")
