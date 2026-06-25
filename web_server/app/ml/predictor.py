"""
app/ml/predictor.py

1. run_daily_prediction: 매일 장 마감 후 XGBoost 예측 -> total_trading_signals upsert
2. calculate_returns: total_trading_signals 내에서 +1/5/20/60일 수익률 계산 후 업데이트
3. aggregate_monthly_performance: 월별 성능 집계 -> model_performance_monthly 저장
4. check_and_retrain: 성능 나쁜 월 이후 자동 재학습
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, UpdateOne

from app.ml.trainer import FEATURE_COLS, LABEL_MAP, KOSPI_STOCKS, _fetch_market_data, _build_features

logger = logging.getLogger(__name__)

# 종목별 yfinance 재시도 설정
_RETRY_COUNT = 3
_RETRY_DELAY = 5  # 초


def _safe(v):
    try:
        f = float(v)
        return None if f != f else round(f, 4)
    except Exception:
        return None


async def _fetch_stock_with_retry(ticker: str, buf_start: str, end_dt: str) -> pd.DataFrame:
    """yfinance 다운로드 실패 시 최대 _RETRY_COUNT 회 재시도"""
    loop = asyncio.get_event_loop()
    last_exc = None
    for attempt in range(1, _RETRY_COUNT + 1):
        try:
            raw = await loop.run_in_executor(
                None,
                lambda t=ticker: yf.download(
                    t, start=buf_start, end=end_dt,
                    interval='1d', progress=False, auto_adjust=True
                )
            )
            if raw is not None and not raw.empty:
                return raw
            # 빈 데이터는 상장폐지 등으로 재시도해도 의미 없으므로 바로 반환
            return pd.DataFrame()
        except Exception as e:
            last_exc = e
            if attempt < _RETRY_COUNT:
                logger.warning(f"[retry {attempt}/{_RETRY_COUNT}] {ticker} 다운로드 실패: {e} - {_RETRY_DELAY}초 후 재시도")
                await asyncio.sleep(_RETRY_DELAY)
            else:
                logger.error(f"[retry 최종 실패] {ticker}: {e}")
    raise last_exc


async def run_daily_prediction(db: AsyncIOMotorDatabase, target_date: str = None):
    """매일 장 마감 후 전 종목 XGBoost 예측 -> total_trading_signals upsert"""
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
    failed_tickers = []

    for ticker, name, code in KOSPI_STOCKS:
        try:
            raw = await _fetch_stock_with_retry(ticker, buf_start, end_dt)
            if raw.empty:
                logger.warning(f"[predictor] {name}({ticker}) 데이터 없음 - 스킵")
                continue

            df = _build_features(raw, market_map, name)
            today_rows = df[df.index.strftime('%Y-%m-%d') == today]
            if today_rows.empty:
                logger.warning(f"[predictor] {name}({ticker}) 오늘({today}) 데이터 없음 - 스킵")
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
                    'ret_1d': None, 'ret_5d': None, 'ret_20d': None, 'ret_60d': None,
                    'is_correct_5d': None,
                }
                await col.update_one(
                    {'stock_name': name, 'predicted_at': predicted_at},
                    {'$set': doc}, upsert=True
                )
                total += 1

        except Exception as e:
            logger.error(f"[predictor] {name}({ticker}) 예측 최종 실패: {e}")
            failed_tickers.append((ticker, name, code))

    # 실패 종목 1회 추가 재시도 (전체 루프 후)
    if failed_tickers:
        logger.warning(f"[predictor] 실패 종목 {len(failed_tickers)}개 재시도: {[n for _, n, _ in failed_tickers]}")
        await asyncio.sleep(10)
        for ticker, name, code in failed_tickers:
            try:
                raw = await _fetch_stock_with_retry(ticker, buf_start, end_dt)
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
                        'ret_1d': None, 'ret_5d': None, 'ret_20d': None, 'ret_60d': None,
                        'is_correct_5d': None,
                    }
                    await col.update_one(
                        {'stock_name': name, 'predicted_at': predicted_at},
                        {'$set': doc}, upsert=True
                    )
                    total += 1
                    logger.info(f"[predictor] 재시도 성공: {name}")
            except Exception as e:
                logger.error(f"[predictor] {name}({ticker}) 재시도도 실패: {e}")

    logger.info(f"[predictor] 완료: {total}건 ({today}), 최종 실패: {len(failed_tickers)}개")

    await calculate_returns(db)


async def calculate_returns(db: AsyncIOMotorDatabase):
    """
    total_trading_signals에서 종목별 매수->매도 포지션 추적으로 수익률 계산
    결과를 각 매수 신호 도큐먼트에 ret_realized / is_correct 필드로 저장
    """
    col = db.total_trading_signals
    pipeline = [
        {'$match': {'signal': {'$in': ['매수', '매도']}}},
        {'$group': {'_id': '$stock_code', 'count': {'$sum': 1}}},
    ]
    codes = [doc['_id'] async for doc in col.aggregate(pipeline)]
    if not codes:
        logger.info("[returns] 매수/매도 신호 없음")
        return

    logger.info(f"[returns] {len(codes)}개 종목 포지션 추적 시작")
    bulk_ops = []

    for code in codes:
        if not code:
            continue
        cursor = col.find(
            {'stock_code': code, 'signal': {'$in': ['매수', '매도']}},
            sort=[('predicted_at', 1)]
        )
        docs = [doc async for doc in cursor]
        if not docs:
            continue

        position = None
        for doc in docs:
            signal = doc.get('signal')
            close = doc.get('close')
            predicted_at = doc.get('predicted_at')
            if close is None or predicted_at is None:
                continue
            close = float(close)

            if signal == '매수' and position is None:
                position = {'doc_id': doc['_id'], 'buy_price': close, 'buy_date': predicted_at}

            elif signal == '매도' and position is not None:
                ret_pct = round((close - position['buy_price']) / position['buy_price'] * 100, 2)
                is_correct = ret_pct > 0
                bulk_ops.append(UpdateOne(
                    {'_id': position['doc_id']},
                    {'$set': {
                        'ret_realized': ret_pct,
                        'is_correct': is_correct,
                        'sell_date': predicted_at,
                        'sell_price': close,
                    }}
                ))
                position = None

        if position is not None:
            latest = await col.find_one(
                {'stock_code': code, 'close': {'$ne': None}},
                sort=[('predicted_at', -1)],
                projection={'close': 1}
            )
            if latest and latest.get('close'):
                latest_close = float(latest['close'])
                unrealized_pct = round((latest_close - position['buy_price']) / position['buy_price'] * 100, 2)
                bulk_ops.append(UpdateOne(
                    {'_id': position['doc_id']},
                    {'$set': {'ret_unrealized': unrealized_pct, 'is_correct': None}}
                ))

    if bulk_ops:
        result = await col.bulk_write(bulk_ops, ordered=False)
        logger.info(f"[returns] 포지션 수익률 업데이트: {result.modified_count}건")
    else:
        logger.info("[returns] 업데이트할 항목 없음")


async def aggregate_monthly_performance(db: AsyncIOMotorDatabase):
    """
    total_trading_signals에서 매수->매도 실현 수익률 기반 월별 집계
    -> model_performance_monthly 저장
    """
    pipeline = [
        {'$match': {'signal': '매수', 'ret_realized': {'$ne': None}}},
        {'$group': {
            '_id': {
                'year': {'$year': '$predicted_at'},
                'month': {'$month': '$predicted_at'},
            },
            'total': {'$sum': 1},
            'correct': {'$sum': {'$cond': ['$is_correct', 1, 0]}},
            'avg_ret': {'$avg': '$ret_realized'},
            'max_ret': {'$max': '$ret_realized'},
            'min_ret': {'$min': '$ret_realized'},
        }},
        {'$sort': {'_id.year': 1, '_id.month': 1}},
    ]
    col_monthly = db.model_performance_monthly
    results = [doc async for doc in db.total_trading_signals.aggregate(pipeline)]
    if not results:
        logger.info("[monthly] 집계할 실현 수익률 없음")
        return

    bulk_ops = []
    for r in results:
        ym = r['_id']
        month_str = f"{ym['year']}-{ym['month']:02d}"
        total = r['total']
        correct = r['correct']
        bulk_ops.append(UpdateOne(
            {'month': month_str},
            {'$set': {
                'month': month_str,
                'year': ym['year'],
                'month_num': ym['month'],
                'total': total,
                'correct': correct,
                'accuracy': round(correct / total * 100, 1) if total > 0 else 0,
                'avg_ret': round(r.get('avg_ret') or 0, 2),
                'max_ret': round(r.get('max_ret') or 0, 2),
                'min_ret': round(r.get('min_ret') or 0, 2),
                'updated_at': datetime.utcnow(),
            }},
            upsert=True
        ))

    await col_monthly.bulk_write(bulk_ops, ordered=False)
    logger.info(f"[monthly] 월별 성능 집계 완료: {len(results)}개월")


async def check_and_retrain(db: AsyncIOMotorDatabase):
    """최근 2개월 매수 신호 정확도가 50% 미만이면 자동 재학습"""
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
        logger.warning("[check_retrain] 정확도 50% 미만 -> 자동 재학습")
        from app.ml.trainer import train_model
        await train_model(db, triggered_by="auto_drift")
