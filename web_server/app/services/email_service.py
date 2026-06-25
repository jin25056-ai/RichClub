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

    boxes = "".join(
        f'<td style="width:48px;height:58px;background:#1a1a2e;border:1.5px solid #6366f1;'
        f'border-radius:10px;text-align:center;vertical-align:middle;'
        f'font-size:28px;font-weight:700;color:#e2e8f0;font-family:monospace;'
        f'padding:0;">{c}</td>'
        f'{"<td width=8></td>" if i < 5 else ""}'
        for i, c in enumerate(code)
    )

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#0a0a14;-webkit-text-size-adjust:100%;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#0a0a14">
  <tr><td align="center" style="padding:48px 20px;">

    <table width="520" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;width:100%;">

      <!-- 로고 -->
      <tr>
        <td style="padding-bottom:20px;">
          <span style="font-size:24px;font-weight:800;color:#ffffff;letter-spacing:-0.03em;font-family:-apple-system,sans-serif;">Rich</span><span style="font-size:24px;font-weight:800;color:#6366f1;letter-spacing:-0.03em;font-family:-apple-system,sans-serif;">Club</span>
        </td>
      </tr>

      <!-- 카드 -->
      <tr>
        <td style="background:#0f0f1a;border:1px solid #1e1e2e;border-radius:16px;overflow:hidden;">

          <!-- 상단 그라디언트 바 -->
          <tr>
            <td height="3" style="background:linear-gradient(90deg,#4f46e5,#6366f1,#818cf8);font-size:0;line-height:0;">&nbsp;</td>
          </tr>

          <!-- 본문 -->
          <tr>
            <td style="padding:40px 40px 32px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">

              <p style="margin:0 0 4px;font-size:11px;font-weight:700;color:#6366f1;letter-spacing:0.12em;text-transform:uppercase;">Email Verification</p>
              <p style="margin:0 0 12px;font-size:26px;font-weight:700;color:#e2e8f0;line-height:1.2;">이메일 인증 코드</p>
              <p style="margin:0 0 32px;font-size:14px;color:#6b7280;line-height:1.7;">아래 코드를 입력창에 입력해 주세요.<br>코드는 <span style="color:#a5b4fc;font-weight:600;">5분간</span> 유효합니다.</p>

              <!-- 코드 박스들 -->
              <table cellpadding="0" cellspacing="0" border="0" style="margin:0 auto 32px;">
                <tr>{boxes}</tr>
              </table>

              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="background:#0a0a14;border:1px solid #1e1e2e;border-radius:8px;padding:14px 16px;">
                    <p style="margin:0;font-size:12px;color:#374151;line-height:1.6;">본인이 요청하지 않은 경우 이 이메일을 무시해 주세요.<br>계정 보안을 위해 코드를 타인과 공유하지 마세요.</p>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- 푸터 -->
          <tr>
            <td style="padding:16px 40px;border-top:1px solid #1e1e2e;">
              <p style="margin:0;font-size:11px;color:#1f2937;font-family:-apple-system,sans-serif;">&copy; 2026 RichClub &nbsp;&middot;&nbsp; AI 기반 주식 분석 플랫폼</p>
            </td>
          </tr>

        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

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
        "email": email,
        "code": code,
        "expires_at": expires_at,
        "verified": False,
    })

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
