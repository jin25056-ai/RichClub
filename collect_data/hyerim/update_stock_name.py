"""
update_stock_name.py
stock_ohlcv_kospi200 컬렉션에 stock_name 필드 추가
- KIS API output1 의 hts_kor_isnm 으로 종목명 조회
- 종목코드별 1회만 호출 (날짜 무관)
- 이미 stock_name 있는 도큐먼트는 스킵
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv
import threading

load_dotenv()

# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------
KIS_APP_KEY    = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_BASE_URL   = os.getenv("KIS_BASE_URL")

MONGO_URI   = os.getenv("MONGO_URI")
DB_NAME     = os.getenv("MONGO_DB_NAME", "data_hyerim")
COLLECTION  = "stock_ohlcv_kospi200"
TOKEN_FILE  = os.path.join(os.path.dirname(__file__), ".kis_token.json")
RATE_LIMIT  = 0.05

today    = datetime.today()
END_DATE = (today - timedelta(days=1)).strftime("%Y%m%d")

# ---------------------------------------------------------------------------
# rate limiter
# ---------------------------------------------------------------------------
_lock      = threading.Lock()
_last_call = [0.0]

def rate_limited_get(url, headers, params):
    with _lock:
        elapsed = time.time() - _last_call[0]
        if elapsed < RATE_LIMIT:
            time.sleep(RATE_LIMIT - elapsed)
        _last_call[0] = time.time()
    return requests.get(url, headers=headers, params=params, timeout=10)


# ---------------------------------------------------------------------------
# mongodb 연결
# ---------------------------------------------------------------------------
def get_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return client[DB_NAME]


# ---------------------------------------------------------------------------
# KIS 토큰 재사용
# ---------------------------------------------------------------------------
def load_token_from_file() -> str | None:
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
        expires_at = datetime.fromisoformat(data["expires_at"])
        if datetime.now() < expires_at - timedelta(minutes=30):
            print(f"[kis] 기존 토큰 재사용 (만료: {expires_at.strftime('%H:%M:%S')})")
            return data["access_token"]
    except Exception:
        pass
    return None


def save_token_to_file(token: str, expires_in: int):
    expires_at = datetime.now() + timedelta(seconds=expires_in)
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "access_token": token,
            "expires_at": expires_at.isoformat(),
        }, f)


def get_kis_token() -> str:
    token = load_token_from_file()
    if token:
        return token

    url = f"{KIS_BASE_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
    }
    res = requests.post(url, headers=headers, json=body, timeout=10)
    res.raise_for_status()
    data       = res.json()
    token      = data.get("access_token")
    expires_in = data.get("expires_in", 86400)
    save_token_to_file(token, expires_in)
    print(f"[kis] 새 토큰 발급 완료 (유효기간: {expires_in//3600}시간)")
    return token


# ---------------------------------------------------------------------------
# KIS 종목명 조회 (1회 호출로 종목명 추출)
# ---------------------------------------------------------------------------
def get_stock_name(token: str, stock_code: str) -> str:
    url = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "FHKST03010100",
        "custtype": "P",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": END_DATE,
        "FID_INPUT_DATE_2": END_DATE,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }
    res = rate_limited_get(url, headers, params)
    res.raise_for_status()
    data = res.json()

    if data.get("rt_cd") != "0":
        return ""

    return data.get("output1", {}).get("hts_kor_isnm", "")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print(f"[start] 종목명 업데이트 (db: {DB_NAME} / collection: {COLLECTION})")
    db         = get_db()
    collection = db[COLLECTION]
    print("[mongo] 연결 완료")

    token = get_kis_token()

    # stock_name 없는 종목코드 목록 조회
    pipeline = [
        {"$match": {"stock_name": {"$exists": False}}},
        {"$group": {"_id": "$stock_code"}},
    ]
    codes_without_name = [doc["_id"] for doc in collection.aggregate(pipeline)]
    print(f"[target] 종목명 없는 종목: {len(codes_without_name)}개")

    for i, code in enumerate(codes_without_name):
        try:
            name = get_stock_name(token, code)
            if name:
                result = collection.update_many(
                    {"stock_code": code},
                    {"$set": {"stock_name": name}}
                )
                print(f"[update] ({i+1}/{len(codes_without_name)}) {code} {name} -> {result.modified_count}건 업데이트")
            else:
                print(f"[skip] ({i+1}/{len(codes_without_name)}) {code} 종목명 조회 실패")
        except Exception as e:
            print(f"[error] ({i+1}/{len(codes_without_name)}) {code} 오류: {e}")

    print("\n[done] 종목명 업데이트 완료")


if __name__ == "__main__":
    main()
