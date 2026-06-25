"""
migrate_predictions.py - bulk_write로 빠른 마이그레이션
"""
import os
import logging
from datetime import datetime, timezone, timedelta

from pymongo import MongoClient, ASCENDING, UpdateOne
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
MONGO_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or ""
DB_NAME = os.getenv("MONGODB_DB") or "richclub"
HOLD_DAYS = 5
BATCH_SIZE = 500


def migrate():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    src = db["total_trading_signals"]
    dst = db["model_predictions"]

    dst.create_index([("stock_name", ASCENDING), ("predicted_at", ASCENDING)], unique=True)

    total = src.count_documents({})
    logger.info(f"total_trading_signals 전체: {total}건")

    inserted = 0
    last_id = None

    while True:
        query = {}
        if last_id:
            query["_id"] = {"$gt": last_id}

        batch = list(src.find(query).sort("_id", 1).limit(BATCH_SIZE))
        if not batch:
            break

        last_id = batch[-1]["_id"]
        ops = []

        for doc in batch:
            name = doc.get("stock_name", "")
            code = doc.get("stock_code", "")
            signal = doc.get("signal", "관망")
            predicted_at = doc.get("predicted_at")
            close_price = doc.get("close")

            if not predicted_at or not close_price:
                continue

            if predicted_at.tzinfo is None:
                predicted_at = predicted_at.replace(tzinfo=timezone.utc)

            evaluate_at = predicted_at + timedelta(days=HOLD_DAYS)

            pred_doc = {
                "stock_code": code,
                "stock_name": name,
                "signal": signal,
                "signal_label": {"매수": 1, "매도": 0, "관망": 2}.get(signal, 2),
                "close_at_prediction": float(close_price),
                "predicted_at": predicted_at,
                "evaluate_at": evaluate_at,
                "actual_return_pct": None,
                "future_close": None,
                "is_correct": None,
                "evaluated": False,
                "migrated": True,
            }

            ops.append(UpdateOne(
                {"stock_name": name, "predicted_at": predicted_at},
                {"$setOnInsert": pred_doc},
                upsert=True,
            ))

        if ops:
            result = dst.bulk_write(ops, ordered=False)
            inserted += result.upserted_count
            logger.info(f"진행: {inserted}건 삽입 / {total}건 (배치 {len(ops)}건)")

    logger.info(f"마이그레이션 완료: {inserted}건 삽입")


if __name__ == "__main__":
    migrate()
