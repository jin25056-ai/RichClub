import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.mongo import get_db

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def collect_market_data() -> None:
    """시장 데이터 수집 - 추후 실제 API 연동"""
    db = get_db()
    doc = {
        "collected_at": datetime.now(timezone.utc),
        "source": "placeholder",
        "data": {},
    }
    await db.market_data.insert_one(doc)
    logger.info("시장 데이터 수집 완료: %s", doc["collected_at"])


def start_scheduler() -> None:
    scheduler.add_job(
        collect_market_data,
        trigger="cron",
        hour="9,15",
        minute="0",
        id="collect_market_data",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("스케줄러 시작")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("스케줄러 종료")
