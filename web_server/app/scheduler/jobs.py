import logging
import subprocess
import sys
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


async def run_drift_check() -> None:
    """
    드리프트 감지 + 필요 시 재학습 실행
    매주 월요일 오전 8시에 실행
    """
    logger.info("드리프트 감지 스케줄 시작")
    db = get_db()
    stdout = ""
    stderr = ""
    status = "failed"

    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.ml.retrain_pipeline"],
            capture_output=True,
            text=True,
            timeout=3600
        )
        stdout = result.stdout
        stderr = result.stderr
        if result.returncode == 0:
            logger.info("드리프트 감지 완료:\n%s", stdout)
            status = "success"
        else:
            logger.error("드리프트 감지 실패:\n%s", stderr)
            status = "failed"

    except subprocess.TimeoutExpired:
        logger.error("드리프트 감지 타임아웃 (1시간 초과)")
        status = "timeout"
    except Exception as e:
        logger.error("드리프트 감지 오류: %s", str(e))
        status = "error"

    await db.drift_check_history.insert_one({
        "checked_at": datetime.now(timezone.utc),
        "status": status,
        "stdout": stdout,
        "stderr": stderr
    })


def start_scheduler() -> None:
    # 시장 데이터 수집 (매일 오전 9시, 오후 3시)
    scheduler.add_job(
        collect_market_data,
        trigger="cron",
        hour="9,15",
        minute="0",
        id="collect_market_data",
        replace_existing=True,
    )

    # 드리프트 감지 (매주 월요일 오전 8시)
    scheduler.add_job(
        run_drift_check,
        trigger="cron",
        day_of_week="mon",
        hour="8",
        minute="0",
        id="drift_check",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("스케줄러 시작")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("스케줄러 종료")
