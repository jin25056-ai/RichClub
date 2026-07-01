import asyncio
import logging
from datetime import datetime, timezone, timedelta

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


async def _send_daily_signal_notification(db, model_id: str, target_date: str) -> None:
    """해당 날짜의 매수/매도 신호만 모아서 텔레그램 알림 전송 (관망 제외)"""
    from app.utils.telegram import notify_signals
    predicted_at = datetime.strptime(target_date, '%Y-%m-%d')
    cursor = db.total_trading_signals.find(
        {'model_id': model_id, 'predicted_at': predicted_at, 'signal': {'$in': ['매수', '매도']}},
        projection={'stock_code': 1, 'stock_name': 1, 'signal': 1, 'close': 1}
    )
    signals = [doc async for doc in cursor]
    if signals:
        await notify_signals(model_id, signals)


async def _has_prediction_today(db, model_id: str, today: str) -> bool:
    """오늘 날짜 예측 데이터가 이미 있는지 확인"""
    predicted_at = datetime.strptime(today, '%Y-%m-%d')
    count = await db.total_trading_signals.count_documents({
        'model_id': model_id,
        'predicted_at': predicted_at,
    })
    return count > 0


async def run_daily_predict() -> None:
    """매일 장 마감 후 전 종목 예측 - 데이터 없으면 10분마다 재시도"""
    import yfinance as yf
    db = get_db()
    from app.ml.predictor import run_daily_prediction

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d')

    while True:
        raw = yf.download('005930.KS', start=today, end=tomorrow,
                          interval='1d', progress=False, auto_adjust=True)
        if not raw.empty:
            logger.info(f"[predictor] {today} 데이터 확인됨, 예측 시작")
            await run_daily_prediction(db, target_date=today)
            await _send_daily_signal_notification(db, 'ju-model-v2', today)
            break
        logger.info(f"[predictor] {today} 데이터 아직 없음, 10분 후 재시도")
        await asyncio.sleep(600)


async def run_daily_seo_predict() -> None:
    """매일 장 마감 후 seo-model-v1 예측 - 데이터 없으면 10분마다 재시도"""
    import yfinance as yf
    db = get_db()
    from app.ml.seo_predictor import run_daily_seo_prediction

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d')

    while True:
        raw = yf.download('005930.KS', start=today, end=tomorrow,
                          interval='1d', progress=False, auto_adjust=True)
        if not raw.empty:
            logger.info(f"[seo_predictor] {today} 데이터 확인됨, 예측 시작")
            await run_daily_seo_prediction(db, model_id="seo-model-v1", target_date=today)
            await _send_daily_signal_notification(db, 'seo-model-v1', today)
            break
        logger.info(f"[seo_predictor] {today} 데이터 아직 없음, 10분 후 재시도")
        await asyncio.sleep(600)


async def run_daily_seo_v2_predict() -> None:
    """매일 장 마감 후 seo-model-v2 예측 - 데이터 없으면 10분마다 재시도"""
    import yfinance as yf
    db = get_db()
    from app.ml.seo_predictor import run_daily_seo_prediction

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d')

    while True:
        raw = yf.download('005930.KS', start=today, end=tomorrow,
                          interval='1d', progress=False, auto_adjust=True)
        if not raw.empty:
            logger.info(f"[seo_predictor_v2] {today} 데이터 확인됨, 예측 시작")
            await run_daily_seo_prediction(db, model_id="seo-model-v2", target_date=today)
            await _send_daily_signal_notification(db, 'seo-model-v2', today)
            break
        logger.info(f"[seo_predictor_v2] {today} 데이터 아직 없음, 10분 후 재시도")
        await asyncio.sleep(600)


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
    db = get_db()
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


async def run_startup_catch_up() -> None:
    """
    서버 시작 시 오늘 예측이 누락된 경우 자동으로 예측 실행.
    배포/재시작으로 스케줄 시간을 놓쳤을 때를 커버함.
    평일(월~금)이고, 현재 UTC 시각이 07:00 이후일 때만 실행.
    """
    import yfinance as yf

    now_utc = datetime.now(timezone.utc)
    # 주말은 스킵
    if now_utc.weekday() >= 5:
        logger.info("[startup_catch_up] 주말 - 스킵")
        return
    # UTC 07:00 이전이면 스킵 (장 마감 데이터가 아직 없을 수 있음)
    if now_utc.hour < 7:
        logger.info("[startup_catch_up] UTC 07:00 이전 - 스킵")
        return

    db = get_db()
    today = now_utc.strftime('%Y-%m-%d')
    tomorrow = (now_utc + timedelta(days=1)).strftime('%Y-%m-%d')

    # yfinance 데이터 확인
    raw = yf.download('005930.KS', start=today, end=tomorrow,
                      interval='1d', progress=False, auto_adjust=True)
    if raw.empty:
        logger.info(f"[startup_catch_up] {today} yfinance 데이터 없음 - 스킵")
        return

    logger.info(f"[startup_catch_up] {today} 누락 예측 체크 시작")

    from app.ml.predictor import run_daily_prediction
    from app.ml.seo_predictor import run_daily_seo_prediction

    # ju-model-v2
    if not await _has_prediction_today(db, 'ju-model-v2', today):
        logger.info(f"[startup_catch_up] ju-model-v2 {today} 예측 누락 -> 실행")
        await run_daily_prediction(db, target_date=today)
        await _send_daily_signal_notification(db, 'ju-model-v2', today)
    else:
        logger.info(f"[startup_catch_up] ju-model-v2 {today} 이미 완료")

    # seo-model-v1
    if not await _has_prediction_today(db, 'seo-model-v1', today):
        logger.info(f"[startup_catch_up] seo-model-v1 {today} 예측 누락 -> 실행")
        await run_daily_seo_prediction(db, model_id="seo-model-v1", target_date=today)
        await _send_daily_signal_notification(db, 'seo-model-v1', today)
    else:
        logger.info(f"[startup_catch_up] seo-model-v1 {today} 이미 완료")

    # seo-model-v2
    if not await _has_prediction_today(db, 'seo-model-v2', today):
        logger.info(f"[startup_catch_up] seo-model-v2 {today} 예측 누락 -> 실행")
        await run_daily_seo_prediction(db, model_id="seo-model-v2", target_date=today)
        await _send_daily_signal_notification(db, 'seo-model-v2', today)
    else:
        logger.info(f"[startup_catch_up] seo-model-v2 {today} 이미 완료")

    logger.info(f"[startup_catch_up] {today} 완료")


def start_scheduler() -> None:
    scheduler.add_job(collect_market_data, trigger="cron",
                      hour="0,6", minute="0", id="collect_market_data", replace_existing=True)

    # ju-model 일별 예측 (KST 15:35 = UTC 06:35)
    scheduler.add_job(run_daily_predict, trigger="cron",
                      day_of_week="mon-fri", hour="6", minute="35",
                      id="run_daily_predict", replace_existing=True,
                      misfire_grace_time=3600)

    # seo-model-v1 일별 예측 (KST 15:40 = UTC 06:40)
    scheduler.add_job(run_daily_seo_predict, trigger="cron",
                      day_of_week="mon-fri", hour="6", minute="40",
                      id="run_daily_seo_predict", replace_existing=True,
                      misfire_grace_time=3600)

    # seo-model-v2 일별 예측 (KST 15:45 = UTC 06:45)
    scheduler.add_job(run_daily_seo_v2_predict, trigger="cron",
                      day_of_week="mon-fri", hour="6", minute="45",
                      id="run_daily_seo_v2_predict", replace_existing=True,
                      misfire_grace_time=3600)

    scheduler.add_job(run_evaluate, trigger="cron",
                      hour="7", minute="0",
                      id="run_evaluate", replace_existing=True)

    scheduler.add_job(run_retrain, trigger="cron",
                      day_of_week="sun", hour="23", minute="0",
                      id="run_retrain", replace_existing=True)

    scheduler.add_job(run_auto_retrain_if_needed, trigger="cron",
                      day_of_week="wed", hour="9", minute="0",
                      id="run_auto_retrain_if_needed", replace_existing=True)

    scheduler.start()
    logger.info("스케줄러 시작")

    # 서버 시작 시 누락된 오늘 예측 자동 실행
    asyncio.get_event_loop().create_task(run_startup_catch_up())


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("스케줄러 종료")
