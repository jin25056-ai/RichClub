import logging
from contextlib import asynccontextmanager
from os import getenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import ASCENDING

from app.api.router import router
from app.db.mongo import close_db, get_db
from app.scheduler.jobs import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    # 버셀 배포 주소 - 환경변수로 추가 가능
    *(getenv("ALLOWED_ORIGINS", "").split(",") if getenv("ALLOWED_ORIGINS") else []),
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
    yield
    stop_scheduler()
    await close_db()
    logger.info("서버 종료")


app = FastAPI(
    title="RichClub API",
    version="0.1.0",
    description="RichClub 백엔드 API 서버",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,  # 쿠키 전송 허용
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
