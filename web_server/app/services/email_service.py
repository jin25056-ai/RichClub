"""
이메일 인증 서비스
- 6자리 인증코드 생성 및 발송
- MongoDB에 임시 저장 (5분 만료)
"""
import random
import smtplib
import string
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings


def _generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _send_email(to: str, code: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "[RichClub] 이메일 인증 코드"
    msg["From"] = settings.email_from
    msg["To"] = to

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0f0f1a;border-radius:12px;color:#e2e8f0;">
      <h2 style="color:#a5b4fc;margin-bottom:8px;">RichClub 이메일 인증</h2>
      <p style="color:#9ca3af;margin-bottom:24px;">아래 인증 코드를 입력해 주세요. 코드는 5분간 유효합니다.</p>
      <div style="background:#1e1e2e;border-radius:8px;padding:20px;text-align:center;letter-spacing:12px;font-size:32px;font-weight:700;color:#6366f1;">
        {code}
      </div>
      <p style="color:#4b5563;font-size:12px;margin-top:24px;">본인이 요청하지 않은 경우 이 이메일을 무시하세요.</p>
    </div>
    """
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.email_from, to, msg.as_string())


async def send_verification_code(db: AsyncIOMotorDatabase, email: str) -> None:
    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    # 기존 코드 삭제 후 새로 저장
    await db.email_verifications.delete_many({"email": email})
    await db.email_verifications.insert_one({
        "email": email,
        "code": code,
        "expires_at": expires_at,
        "verified": False,
    })

    # TTL 인덱스 (자동 만료)
    await db.email_verifications.create_index(
        "expires_at", expireAfterSeconds=0
    )

    _send_email(email, code)


async def verify_code(db: AsyncIOMotorDatabase, email: str, code: str) -> bool:
    doc = await db.email_verifications.find_one({
        "email": email,
        "code": code,
        "verified": False,
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
    if not doc:
        return False

    await db.email_verifications.update_one(
        {"_id": doc["_id"]},
        {"$set": {"verified": True}},
    )
    return True


async def is_email_verified(db: AsyncIOMotorDatabase, email: str) -> bool:
    doc = await db.email_verifications.find_one({
        "email": email,
        "verified": True,
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
    return doc is not None
