"""
5분봉 데이터 수집 스케줄러
- 장 중(오전 9시 ~ 오후 3시 30분) 5분마다 실행
- total_trading_signals 컬렉션의 종목 기준으로 수집
- 30일 초과 데이터 자동 삭제 (Rolling)
"""
import logging
import asyncio
from datetime import datetime, timedelta, timezone

import yfinance as yf
import pandas as pd
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

KEEP_DAYS = 30  # 보관 일수


def _is_market_hour() -> bool:
    """한국 장 시간 여부 (KST 09:00 ~ 15:35)"""
    now_kst = datetime.now(timezone.utc) + timedelta(hours=9)
    weekday = now_kst.weekday()
    if weekday >= 5:  # 토/일
        return False
    market_open = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now_kst.replace(hour=15, minute=35, second=0, microsecond=0)
    return market_open <= now_kst <= market_close


async def _get_target_stocks(db: AsyncIOMotorDatabase) -> list:
    """total_trading_signals에서 종목코드 목록 조회"""
    pipeline = [
        {"$group": {"_id": "$stock_code", "stock_name": {"$first": "$stock_name"}}},
        {"$sort": {"_id": 1}},
    ]
    cursor = db.total_trading_signals.aggregate(pipeline)
    stocks = []
    async for doc in cursor:
        if doc["_id"]:
            stocks.append({"stock_code": doc["_id"], "stock_name": doc.get("stock_name", "")})
    return stocks


def _fetch_5min_data(stock_code: str) -> list:
    """
    yfinance로 5분봉 데이터 수집
    한국 종목코드 → yfinance 티커 변환 (예: 005930 → 005930.KS)
    """
    ticker = f"{stock_code}.KS"
    try:
        df = yf.download(
            ticker,
            period="1d",
            interval="5m",
            progress=False,
            auto_adjust=True
        )
        if df is None or df.empty:
            return []

        records = []
        for dt_idx, row in df.iterrows():
            # timezone-aware datetime
            if hasattr(dt_idx, 'to_pydatetime'):
                dt = dt_idx.to_pydatetime()
            else:
                dt = pd.Timestamp(dt_idx).to_pydatetime()

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            records.append({
                "stock_code": stock_code,
                "datetime": dt,
                "open": float(row["Open"]) if not pd.isna(row["Open"]) else None,
                "high": float(row["High"]) if not pd.isna(row["High"]) else None,
                "low": float(row["Low"]) if not pd.isna(row["Low"]) else None,
                "close": float(row["Close"]) if not pd.isna(row["Close"]) else None,
                "volume": float(row["Volume"]) if not pd.isna(row["Volume"]) else None,
                "interval": "5m",
            })
        return records
    except Exception as e:
        logger.warning(f"5분봉 수집 실패 {stock_code}: {e}")
        return []


async def collect_5min_candles(db: AsyncIOMotorDatabase) -> None:
    """
    5분봉 수집 메인 함수
    - 장 중에만 실행
    - 중복 방지: datetime + stock_code 기준 upsert
    - 30일 초과 데이터 삭제
    """
    if not _is_market_hour():
        logger.debug("장 시간 외. 5분봉 수집 생략.")
        return

    logger.info("5분봉 수집 시작")

    # 수집 대상 종목
    stocks = await _get_target_stocks(db)
    if not stocks:
        logger.warning("수집 대상 종목 없음")
        return

    col = db.candles_5m

    # 인덱스 생성 (최초 1회)
    await col.create_index(
        [("stock_code", 1), ("datetime", 1)],
        unique=True,
        name="idx_stock_datetime"
    )
    await col.create_index([("datetime", 1)], name="idx_datetime")

    # 종목별 수집 (yfinance 과부하 방지: 배치 처리)
    total_inserted = 0
    loop = asyncio.get_event_loop()

    for stock in stocks:
        stock_code = stock["stock_code"]
        try:
            records = await loop.run_in_executor(
                None, _fetch_5min_data, stock_code
            )
            if not records:
                continue

            # upsert (중복 방지)
            for rec in records:
                await col.update_one(
                    {"stock_code": rec["stock_code"], "datetime": rec["datetime"]},
                    {"$set": rec},
                    upsert=True
                )
            total_inserted += len(records)

        except Exception as e:
            logger.error(f"5분봉 저장 실패 {stock_code}: {e}")

        # 과부하 방지 딜레이
        await asyncio.sleep(0.3)

    logger.info(f"5분봉 수집 완료: {total_inserted}건 upsert")

    # 30일 초과 데이터 삭제 (Rolling)
    await _delete_old_candles(db)


async def _delete_old_candles(db: AsyncIOMotorDatabase) -> None:
    """30일 초과 5분봉 데이터 삭제"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    result = await db.candles_5m.delete_many({"datetime": {"$lt": cutoff}})
    if result.deleted_count > 0:
        logger.info(f"30일 초과 5분봉 삭제: {result.deleted_count}건")
