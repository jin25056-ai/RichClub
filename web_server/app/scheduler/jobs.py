import logging
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.mongo import get_db
from app.scheduler.candle_collector import collect_5min_candles

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone='UTC')


async def run_5min_candle_collection() -> None:
    db = get_db()
    await collect_5min_candles(db)


async def collect_market_data() -> None:
    logger.info("시장 데이터 수집 시작")


async def run_daily_predict() -> None:
    """매일 장 마감 후 전 종목 예측 (KST 15:35 = UTC 06:35)"""
    db = get_db()
    from app.ml.predictor import run_daily_prediction
    await run_daily_prediction(db)


async def run_evaluate() -> None:
    """매일 수익률 계산 + 월별 집계 (UTC 07:00)"""
    db = get_db()
    from app.ml.predictor import calculate_returns, aggregate_monthly_performance
    await calculate_returns(db)
    await aggregate_monthly_performance(db)


async def run_retrain() -> None:
    """매주 일요일 성능 체크 후 필요시 재학습 (UTC 23:00)"""
    db = get_db()
    from app.ml.predictor import check_and_retrain
    await check_and_retrain(db)


async def run_auto_retrain_if_needed() -> None:
    """
    예측 정확도가 50% 미만이면 자동 재학습 트리거
    매주 수요일 점검
    """
    db = get_db()
    from datetime import datetime, timezone, timedelta
    since = datetime.now(timezone.utc) - timedelta(days=7)
    pipeline = [
        {'$match': {'predicted_at': {'$gte': since}, 'evaluated': True}},
        {'$group': {
            '_id': None,
            'total': {'$sum': 1},
            'correct': {'$sum': {'$cond': ['$is_correct', 1, 0]}},
        }},
    ]
    agg = [doc async for doc in db.model_predictions.aggregate(pipeline)]
    if not agg:
        return
    row = agg[0]
    total = row['total']
    if total < 20:
        return
    acc = row['correct'] / total
    logger.info(f"[auto_retrain] 최근 7일 정확도: {acc:.2%} ({row['correct']}/{total})")
    if acc < 0.50:
        logger.warning(f"[auto_retrain] 정확도 50% 미만 -> 자동 재학습 트리거")
        from app.ml.trainer import train_model
        await train_model(db, triggered_by="auto_drift")


def start_scheduler() -> None:
    # 글로벌 시장 (UTC 00:00, 06:00)
    scheduler.add_job(collect_market_data, trigger="cron",
                      hour="0,6", minute="0", id="collect_market_data", replace_existing=True)

    # 5분봉 수집 (월~금 항상, upsert)
    # misfire_grace_time=240: 서버 재시작으로 놓쳐도 4분 이내면 재실행
    scheduler.add_job(run_5min_candle_collection, trigger="cron",
                      day_of_week="mon-fri", minute="*/5",
                      id="collect_5min_candles", replace_existing=True,
                      misfire_grace_time=240)

    # 일별 예측 (KST 15:35 = UTC 06:35) - 장 마감 5분 후
    # misfire_grace_time=3600: 서버 재시작 등으로 놓친 경우 1시간 이내면 재실행
    scheduler.add_job(run_daily_predict, trigger="cron",
                      day_of_week="mon-fri", hour="6", minute="35",
                      id="daily_predict", replace_existing=True,
                      misfire_grace_time=3600)

    # 예측 성능 평가 (UTC 07:00) - 예측 완료 후 25분 뒤
    scheduler.add_job(run_evaluate, trigger="cron",
                      hour="7", minute="0",
                      id="evaluate_predictions", replace_existing=True)

    # 주간 재학습 (일요일 UTC 23:00)
    scheduler.add_job(run_retrain, trigger="cron",
                      day_of_week="sun", hour="23", minute="0",
                      id="weekly_retrain", replace_existing=True)

    # 자동 재학습 체크 (수요일 UTC 09:00)
    scheduler.add_job(run_auto_retrain_if_needed, trigger="cron",
                      day_of_week="wed", hour="9", minute="0",
                      id="auto_retrain_check", replace_existing=True)

    scheduler.start()
    logger.info("스케줄러 시작")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("스케줄러 종료")
