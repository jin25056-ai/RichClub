"""
app/utils/telegram.py

텔레그램 봇 유틸리티.
- 매수/매도 신호 알림 전송
- 관리자 명령어 처리 (/predict, /retrain, /status, /subscribe, /unsubscribe)

환경변수:
  TELEGRAM_BOT_TOKEN   : @BotFather에서 발급받은 봇 토큰
  TELEGRAM_CHAT_ID     : 기본 알림 채널 chat_id
  TELEGRAM_ADMIN_IDS   : 관리자 chat_id 목록 (쉼표 구분, 예: "12345,67890")
  TELEGRAM_WEBHOOK_URL : webhook 등록용 서버 URL (예: https://richclub.efforthye.dev)
"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ADMIN_IDS = set(
    x.strip() for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip()
)

# 구독자 목록 (메모리 캐시, 재시작 시 초기화됨)
_subscribers: set = set()


# ── 기본 전송 ──────────────────────────────────────────────────────────────

async def send_telegram_message(text: str, chat_id: Optional[str] = None) -> bool:
    """텔레그램으로 메시지 전송. 토큰/chat_id 미설정 시 False 반환."""
    if not TELEGRAM_BOT_TOKEN:
        logger.debug("[telegram] TELEGRAM_BOT_TOKEN 미설정 - 알림 스킵")
        return False

    target = chat_id or TELEGRAM_CHAT_ID
    if not target:
        logger.debug("[telegram] chat_id 없음 - 알림 스킵")
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": target,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        if res.status_code != 200:
            logger.warning(f"[telegram] 전송 실패 ({res.status_code}): {res.text}")
            return False
        return True
    except Exception as e:
        logger.warning(f"[telegram] 전송 예외: {e}")
        return False


async def broadcast(text: str) -> None:
    """기본 채널 + 모든 구독자에게 메시지 전송."""
    await send_telegram_message(text)
    for sub_id in list(_subscribers):
        await send_telegram_message(text, chat_id=sub_id)


# ── 신호 알림 ──────────────────────────────────────────────────────────────

async def notify_signals(model_id: str, signals: list) -> None:
    """매수/매도 신호 리스트를 텔레그램으로 알림 (관망 제외)."""
    buys = [s for s in signals if s.get("signal") == "매수"]
    sells = [s for s in signals if s.get("signal") == "매도"]
    if not buys and not sells:
        return

    lines = [f"<b>[{model_id}] 오늘의 매매 신호</b>"]

    if buys:
        lines.append(f"\n<b>매수 ({len(buys)}건)</b>")
        for s in buys:
            price = f"{int(s['close']):,}원" if s.get("close") else "-"
            lines.append(
                f"· {s.get('stock_name', s.get('stock_code'))} ({s.get('stock_code')}) {price}"
            )

    if sells:
        lines.append(f"\n<b>매도 ({len(sells)}건)</b>")
        for s in sells:
            price = f"{int(s['close']):,}원" if s.get("close") else "-"
            lines.append(
                f"· {s.get('stock_name', s.get('stock_code'))} ({s.get('stock_code')}) {price}"
            )

    await broadcast("\n".join(lines))
    logger.info(f"[telegram] [{model_id}] 알림 전송: 매수 {len(buys)}건, 매도 {len(sells)}건")


# ── 관리자 권한 ────────────────────────────────────────────────────────────

def is_admin(chat_id: str) -> bool:
    """관리자 여부 확인."""
    return str(chat_id) in TELEGRAM_ADMIN_IDS


# ── 명령어 핸들러 ──────────────────────────────────────────────────────────

async def handle_command(update: dict, db) -> None:
    """
    텔레그램 webhook update 처리.

    누구나 사용 가능:
      /start       - 봇 소개 및 명령어 안내
      /subscribe   - 매수/매도 알림 구독
      /unsubscribe - 구독 해제
      /status      - 서버 및 예측 현황 조회

    관리자 전용 (TELEGRAM_ADMIN_IDS에 등록된 chat_id):
      /predict     - 전체 모델 즉시 예측 실행 후 알림
      /retrain     - ju-model-v2 즉시 재학습
    """
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()
    if not text.startswith("/"):
        return

    cmd = text.split()[0].lower().split("@")[0]

    if cmd == "/start":
        await send_telegram_message(
            "<b>RichClub AI 알림 봇</b>\n\n"
            "사용 가능한 명령어\n"
            "/subscribe - 매수/매도 알림 구독\n"
            "/unsubscribe - 구독 해제\n"
            "/status - 서버 상태 및 예측 현황\n\n"
            "<i>관리자 전용: /predict, /retrain</i>",
            chat_id=chat_id,
        )

    elif cmd == "/subscribe":
        _subscribers.add(chat_id)
        await send_telegram_message(
            "구독 완료. 매일 장 마감 후 매수/매도 신호 발생 시 알림을 받습니다.",
            chat_id=chat_id,
        )
        logger.info(f"[telegram] 구독 추가: {chat_id} (총 {len(_subscribers)}명)")

    elif cmd == "/unsubscribe":
        _subscribers.discard(chat_id)
        await send_telegram_message("구독이 해제되었습니다.", chat_id=chat_id)
        logger.info(f"[telegram] 구독 해제: {chat_id} (총 {len(_subscribers)}명)")

    elif cmd == "/status":
        try:
            from datetime import datetime, timezone, timedelta
            since = datetime.now(timezone.utc) - timedelta(days=1)
            lines = ["<b>RichClub 서버 상태</b>\n"]
            for m in ["ju-model-v2", "seo-model-v1", "seo-model-v2"]:
                c = await db.total_trading_signals.count_documents(
                    {"model_id": m, "predicted_at": {"$gte": since}}
                )
                lines.append(f"· {m}: {c}건 (최근 24h)")
            lines.append(f"\n구독자 수: {len(_subscribers)}명")
            await send_telegram_message("\n".join(lines), chat_id=chat_id)
        except Exception as e:
            await send_telegram_message(f"상태 조회 실패: {e}", chat_id=chat_id)

    elif cmd == "/predict":
        if not is_admin(chat_id):
            await send_telegram_message("관리자 전용 명령어입니다.", chat_id=chat_id)
            return
        await send_telegram_message("예측을 시작합니다...", chat_id=chat_id)
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            from app.ml.predictor import run_daily_prediction
            from app.ml.seo_predictor import run_daily_seo_prediction

            await run_daily_prediction(db, target_date=today)
            await run_daily_seo_prediction(db, model_id="seo-model-v1", target_date=today)
            await run_daily_seo_prediction(db, model_id="seo-model-v2", target_date=today)
            await send_telegram_message(f"전체 예측 완료 ({today})", chat_id=chat_id)

            from datetime import datetime as _dt
            predicted_at = _dt.strptime(today, "%Y-%m-%d")
            for model_id in ["ju-model-v2", "seo-model-v1", "seo-model-v2"]:
                cursor = db.total_trading_signals.find(
                    {
                        "model_id": model_id,
                        "predicted_at": predicted_at,
                        "signal": {"$in": ["매수", "매도"]},
                    },
                    projection={"stock_code": 1, "stock_name": 1, "signal": 1, "close": 1},
                )
                signals = [doc async for doc in cursor]
                if signals:
                    await notify_signals(model_id, signals)

        except Exception as e:
            await send_telegram_message(f"예측 실패: {e}", chat_id=chat_id)
            logger.error(f"[telegram] /predict 실패: {e}")

    elif cmd == "/retrain":
        if not is_admin(chat_id):
            await send_telegram_message("관리자 전용 명령어입니다.", chat_id=chat_id)
            return
        await send_telegram_message(
            "재학습을 시작합니다. 완료까지 시간이 걸릴 수 있습니다...",
            chat_id=chat_id,
        )
        try:
            from app.ml.trainer import train_model
            await train_model(db, triggered_by="telegram_admin")
            await send_telegram_message("재학습 완료", chat_id=chat_id)
        except Exception as e:
            await send_telegram_message(f"재학습 실패: {e}", chat_id=chat_id)
            logger.error(f"[telegram] /retrain 실패: {e}")

    else:
        await send_telegram_message(
            "알 수 없는 명령어입니다. /start 로 도움말을 확인하세요.",
            chat_id=chat_id,
        )


# ── Webhook 등록 ──────────────────────────────────────────────────────────

async def set_webhook(webhook_url: str) -> bool:
    """텔레그램 webhook URL 등록."""
    if not TELEGRAM_BOT_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
                json={"url": webhook_url},
            )
        ok = res.status_code == 200
        if ok:
            logger.info(f"[telegram] Webhook 등록 완료: {webhook_url}")
        else:
            logger.warning(f"[telegram] Webhook 등록 실패: {res.text}")
        return ok
    except Exception as e:
        logger.warning(f"[telegram] Webhook 등록 예외: {e}")
        return False
