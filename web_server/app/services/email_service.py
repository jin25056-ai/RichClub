"""
이메일 인증 서비스
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

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background-color:#0a0a14;" bgcolor="#0a0a14">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#0a0a14" style="background-color:#0a0a14;">
  <tr><td align="center" style="padding:40px 16px;">
    <table width="480" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;width:100%;">
      <tr>
        <td bgcolor="#0f0f1a" style="background-color:#0f0f1a;border:1px solid #1e1e2e;border-radius:12px;padding:40px 36px;">
          <p style="margin:0 0 4px;font-size:11px;font-weight:700;color:#6366f1;letter-spacing:0.1em;font-family:-apple-system,sans-serif;">RICHCLUB</p>
          <p style="margin:0 0 20px;font-size:22px;font-weight:700;color:#e2e8f0;font-family:-apple-system,sans-serif;">이메일 인증</p>
          <p style="margin:0 0 28px;font-size:14px;color:#6b7280;line-height:1.7;font-family:-apple-system,sans-serif;">아래 코드를 입력해 주세요. 코드는 <span style="color:#a5b4fc;">5분</span>이 지나면 만료됩니다.</p>
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td bgcolor="#1a1a2e" style="background-color:#1a1a2e;border:1px solid #2d2d3d;border-radius:10px;padding:24px;text-align:center;">
                <span style="font-size:32px;font-weight:800;color:#e2e8f0;letter-spacing:14px;font-family:monospace;">{code}</span>
              </td>
            </tr>
          </table>
          <p style="margin:24px 0 0;font-size:12px;color:#374151;font-family:-apple-system,sans-serif;">본인이 요청하지 않은 경우 이 메일을 무시해 주세요.</p>
        </td>
      </tr>
      <tr><td style="padding-top:16px;text-align:center;">
        <p style="margin:0;font-size:11px;color:#1f2937;font-family:-apple-system,sans-serif;">&copy; 2026 RichClub</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""

    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.email_from, to, msg.as_string())


async def send_verification_code(db: AsyncIOMotorDatabase, email: str) -> None:
    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    await db.email_verifications.delete_many({"email": email})
    await db.email_verifications.insert_one({
        "email": email, "code": code,
        "expires_at": expires_at, "verified": False,
    })
    await db.email_verifications.create_index("expires_at", expireAfterSeconds=0)
    _send_email(email, code)


async def verify_code(db: AsyncIOMotorDatabase, email: str, code: str) -> bool:
    doc = await db.email_verifications.find_one({
        "email": email, "code": code, "verified": False,
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
    if not doc:
        return False
    await db.email_verifications.update_one({"_id": doc["_id"]}, {"$set": {"verified": True}})
    return True


async def is_email_verified(db: AsyncIOMotorDatabase, email: str) -> bool:
    doc = await db.email_verifications.find_one({
        "email": email, "verified": True,
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
    return doc is not None
