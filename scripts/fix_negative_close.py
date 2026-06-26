"""
MongoDB에서 seo-model-v1의 음수 close 값을 양수로 변환하는 스크립트
close가 음수인 경우 절댓값으로 교체
"""
import logging
from pymongo import MongoClient, UpdateOne

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MONGODB_URI = "mongodb+srv://richclub_user:wBzJQpD2lcz1vMBE@datacluster0.5v6tfgd.mongodb.net"
MONGODB_DB  = "richclub"

def main():
    client = MongoClient(MONGODB_URI)
    col = client[MONGODB_DB]["total_trading_signals"]

    query = {"close": {"$lt": 0}, "model_id": "seo-model-v1"}
    total = col.count_documents(query)
    logger.info(f"음수 close 건수: {total}")

    if total == 0:
        logger.info("수정할 데이터 없음")
        client.close()
        return

    bulk_ops = []
    fixed = 0

    for doc in col.find(query, {"_id": 1, "close": 1}):
        bulk_ops.append(UpdateOne(
            {"_id": doc["_id"]},
            {"$set": {"close": abs(doc["close"])}}
        ))
        if len(bulk_ops) >= 1000:
            col.bulk_write(bulk_ops, ordered=False)
            fixed += len(bulk_ops)
            bulk_ops = []
            logger.info(f"  진행: {fixed}/{total}")

    if bulk_ops:
        col.bulk_write(bulk_ops, ordered=False)
        fixed += len(bulk_ops)

    logger.info(f"완료 - {fixed}건 수정")
    client.close()

if __name__ == "__main__":
    main()
