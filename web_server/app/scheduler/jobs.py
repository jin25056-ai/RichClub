import logging
import asyncio
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.mongo import get_db
from app.scheduler.candle_collector import collect_5min_candles
from app.scheduler.daily_collector import collect_daily_signals

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone='UTC')


async def run_5min_candle_collection() -> None:
    db = get_db()
    await collect_5min_candles(db)


async def collect_market_data() -> None:
    logger.info("시장 데이터 수집 시작")


async def run_daily_collect() -> None:
    """매일 장 마감 후 오늘 날짜 신호 수집 (월~금 KST 16:30 = UTC 07:30)"""
    db = get_db()
    await collect_daily_signals(db)


async def run_drift_check() -> None:
    logger.info("드리프트 감지 실행")


def start_scheduler() -> None:
    # 글로벌 시장 데이터 수집 (UTC 00:00, 06:00 = KST 09:00, 15:00)
    scheduler.add_job(
        collect_market_data,
        trigger="cron",
        hour="0,6",
        minute="0",
        id="collect_market_data",
        replace_existing=True,
    )

    # 5분봉 수집: 항상 5분마다 (장 외 시간도 수집, upsert로 중복 방지)
    scheduler.add_job(
        run_5min_candle_collection,
        trigger="cron",
        day_of_week="mon-fri",
        minute="*/5",
        id="collect_5min_candles",
        replace_existing=True,
    )

    # 일별 신호 수집 (월~금 KST 16:30 = UTC 07:30)
    scheduler.add_job(
        run_daily_collect,
        trigger="cron",
        day_of_week="mon-fri",
        hour="7",
        minute="30",
        id="daily_collect",
        replace_existing=True,
    )

    # 드리프트 감지 (매주 월요일 UTC 23:00 = KST 월 08:00)
    scheduler.add_job(
        run_drift_check,
        trigger="cron",
        day_of_week="sun",
        hour="23",
        minute="0",
        id="drift_check",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("스케줄러 시작")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("스케줄러 종료")
