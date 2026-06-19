import logging
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import hash_password, verify_password
from app.schemas.auth import UserCreate

logger = logging.getLogger(__name__)


async def find_user_by_email(db: AsyncIOMotorDatabase, email: str) -> dict | None:
    return await db.users.find_one({"email": email})


async def find_user_by_id(db: AsyncIOMotorDatabase, user_id: str) -> dict | None:
    try:
        return await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


async def create_user(db: AsyncIOMotorDatabase, data: UserCreate) -> dict:
    existing = await find_user_by_email(db, data.email)
    logger.info("[create_user] email=%s existing=%s", data.email, existing)
    if existing:
        raise ValueError("이미 사용 중인 이메일입니다.")

    doc = {
        "email": data.email,
        "hashed_password": hash_password(data.password),
        "name": data.name,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info("[create_user] 생성 완료 id=%s", result.inserted_id)
    return doc


async def authenticate_user(
    db: AsyncIOMotorDatabase, email: str, password: str
) -> dict | None:
    user = await find_user_by_email(db, email)
    if not user:
        return None
    if not user.get("is_active", True):
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def serialize_user(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "name": doc["name"],
        "created_at": doc["created_at"],
    }
