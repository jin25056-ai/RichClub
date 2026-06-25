"""
5분봉 데이터 수집 스케줄러
- 장 중(KST 09:00~15:35 = UTC 00:00~06:35) 5분마다 실행
- total_trading_signals 컬렉션의 종목 기준으로 수집
- 30일 초과 데이터 자동 삭제
"""
import logging
import asyncio
from datetime import datetime, timedelta, timezone

import yfinance as yf
import pandas as pd
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

KEEP_DAYS = 90


async def _get_target_stocks(db: AsyncIOMotorDatabase) -> list:
    """total_trading_signals에서 종목코드 목록 조회"""
    pipeline = [
        {"$group": {"_id": "$stock_code", "stock_name": {"$first": "$stock_name"}}},
        {"$sort": {"_id": 1}},
    ]
    cursor = db.total_trading_signals.aggregate(pipeline)
    stocks = []
    async for doc in cursor:
        code = doc["_id"]
        # 6자리 숫자 코드만 수집
        if code and code.isdigit() and len(code) == 6:
            stocks.append({"stock_code": code, "stock_name": doc.get("stock_name", "")})
    return stocks


def _fetch_5min_data(stock_code: str) -> list:
    """yfinance로 5분봉 수집"""
    ticker = f"{stock_code}.KS"
    try:
        df = yf.download(ticker, period="1d", interval="5m", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return []

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        records = []
        for dt_idx, row in df.iterrows():
            dt = dt_idx.to_pydatetime() if hasattr(dt_idx, 'to_pydatetime') else pd.Timestamp(dt_idx).to_pydatetime()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            records.append({
                "stock_code": stock_code,
                "datetime": dt,
                "open":   float(row.get("Open",   row.get("open",   0))) if not pd.isna(row.get("Open",   row.get("open",   float('nan')))) else None,
                "high":   float(row.get("High",   row.get("high",   0))) if not pd.isna(row.get("High",   row.get("high",   float('nan')))) else None,
                "low":    float(row.get("Low",    row.get("low",    0))) if not pd.isna(row.get("Low",    row.get("low",    float('nan')))) else None,
                "close":  float(row.get("Close",  row.get("close",  0))) if not pd.isna(row.get("Close",  row.get("close",  float('nan')))) else None,
                "volume": float(row.get("Volume", row.get("volume", 0))) if not pd.isna(row.get("Volume", row.get("volume", float('nan')))) else None,
                "interval": "5m",
            })
        return records
    except Exception as e:
        logger.warning(f"5분봉 수집 실패 {stock_code}: {e}")
        return []


async def collect_5min_candles(db: AsyncIOMotorDatabase) -> None:
    """5분봉 수집 메인 함수 (스케줄러에서 시간 제어하므로 여기서는 바로 실행)"""
    logger.info("5분봉 수집 시작")

    stocks = await _get_target_stocks(db)
    if not stocks:
        logger.warning("수집 대상 종목 없음")
        return

    col = db.candles_5m
    await col.create_index([("stock_code", 1), ("datetime", 1)], unique=True, name="idx_stock_datetime")
    await col.create_index([("datetime", 1)], name="idx_datetime")

    total_inserted = 0
    loop = asyncio.get_event_loop()

    for stock in stocks:
        stock_code = stock["stock_code"]
        try:
            records = await loop.run_in_executor(None, _fetch_5min_data, stock_code)
            for rec in records:
                await col.update_one(
                    {"stock_code": rec["stock_code"], "datetime": rec["datetime"]},
                    {"$set": rec},
                    upsert=True,
                )
            total_inserted += len(records)
        except Exception as e:
            logger.error(f"5분봉 저장 실패 {stock_code}: {e}")
        await asyncio.sleep(0.2)

    logger.info(f"5분봉 수집 완료: {total_inserted}건 upsert")
    await _delete_old_candles(db)


async def _delete_old_candles(db: AsyncIOMotorDatabase) -> None:
    """30일 초과 5분봉 삭제"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    result = await db.candles_5m.delete_many({"datetime": {"$lt": cutoff}})
    if result.deleted_count > 0:
        logger.info(f"30일 초과 5분봉 삭제: {result.deleted_count}건")
