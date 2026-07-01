import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING

from app.api.router import router
from app.db.mongo import close_db, get_db
from app.scheduler.jobs import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://rich-club-front-end.vercel.app",
    "https://richclub-client.efforthye.dev",
    "https://richclub.mayo.im",
    *(os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else []),
]


async def _ensure_indexes() -> None:
    db = get_db()
    await db.users.create_index([("email", ASCENDING)], unique=True, name="idx_users_email")
    logger.info("[MongoDB] 인덱스 설정 완료")


async def _test_mongodb_connection() -> None:
    db = get_db()
    await db.command("ping")
    logger.info("[MongoDB] ping 성공")
    collections = await db.list_collection_names()
    logger.info("[MongoDB] 컬렉션 목록: %s", collections if collections else "(없음 - 첫 실행)")
    user_count = await db.users.count_documents({})
    logger.info("[MongoDB] users 도큐먼트 수: %d", user_count)
    result = await db.connection_test.insert_one({"test": True, "source": "startup"})
    found = await db.connection_test.find_one({"_id": result.inserted_id})
    await db.connection_test.delete_one({"_id": result.inserted_id})
    if found:
        logger.info("[MongoDB] insert/find/delete 테스트 성공")
    else:
        raise RuntimeError("MongoDB 읽기 테스트 실패")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MongoDB 연결 테스트 중...")
    await _test_mongodb_connection()
    await _ensure_indexes()
    logger.info("MongoDB 연결 완료")
    start_scheduler()

    # 텔레그램 webhook 등록 (환경변수 설정 시)
    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL", "")
    if webhook_url:
        from app.utils.telegram import set_webhook
        await set_webhook(f"{webhook_url}/telegram/webhook")

    yield
    stop_scheduler()
    await close_db()
    logger.info("서버 종료")


app = FastAPI(
    title="RichClub API",
    version="0.1.0",
    description="""
## RichClub AI - 주식 AI 분석 플랫폼

**본 서비스는 개발 포트폴리오 데모 프로젝트입니다.**

- AI 예측 결과는 참고용이며 실제 투자 조언이 아닙니다.
- 본 서비스는 투자자문업 등록 또는 유사투자자문업 신고를 하지 않은 데모 서비스입니다.
- 투자 결정은 본인 판단과 책임 하에 신중하게 내리시기 바랍니다.
- 과거 AI 예측 성과가 미래 수익을 보장하지 않습니다.

> This is a portfolio demo project. AI predictions are for reference only and do not constitute investment advice.
    """,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def _db() -> AsyncIOMotorDatabase:
    return get_db()


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.post("/telegram/webhook", tags=["telegram"])
async def telegram_webhook(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(_db),
):
    """텔레그램 webhook 수신 엔드포인트."""
    update = await request.json()
    from app.utils.telegram import handle_command
    await handle_command(update, db)
    return {"ok": True}
