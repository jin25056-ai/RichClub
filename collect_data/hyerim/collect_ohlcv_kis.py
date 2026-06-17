"""
collect_ohlcv_kis.py
KIS API - 국내주식기간별시세(일/주/월/년) [v1_국내주식-016]
코스피200 종목 5년치 일봉 수집
- 토큰 파일 저장/재사용 (만료 시에만 재발급)
- 500 오류 시 스킵 후 계속 진행
- resume 가능
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from pymongo import MongoClient, UpdateOne
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
BATCH_SIZE  = 500
RATE_LIMIT  = 0.05
PAGE_DAYS   = 140

TOKEN_FILE  = os.path.join(os.path.dirname(__file__), ".kis_token.json")

today      = datetime.today()
END_DATE   = (today - timedelta(days=1)).strftime("%Y%m%d")
START_DATE = (today - timedelta(days=365 * 5)).strftime("%Y%m%d")

# ---------------------------------------------------------------------------
# 코스피200 종목코드 리스트
# ---------------------------------------------------------------------------
KOSPI200_CODES = [
    "005930", "000660", "005380", "051910", "035420",
    "005490", "068270", "207940", "006400", "028260",
    "032830", "003550", "012330", "066570", "009150",
    "055550", "034730", "015760", "086790", "105560",
    "017670", "034020", "011200", "010130", "010140",
    "010120", "267260", "042660", "329180", "316140",
    "009540", "042700", "000810", "011070", "006800",
    "000150", "064350", "267250", "079550", "272210",
    "033780", "138040", "307950", "096770", "003670",
    "024110", "035720", "018260", "086280", "000720",
    "047810", "278470", "030200", "071050", "006260",
    "010950", "005940", "323410", "259960", "016360",
    "047050", "003490", "028050", "047040", "005830",
    "039490", "352820", "000880", "007660", "064400",
    "003230", "353200", "161390", "180640", "001440",
    "267270", "009830", "078930", "011790", "326030",
    "004170", "000990", "034220", "032640", "377300",
    "090430", "241560", "021240", "000100", "029780",
    "010060", "138930", "066970", "023530", "082740",
    "036570", "128940", "001040", "271560", "175330",
    "052690", "088980", "088350", "018880", "336260",
    "000500", "002380", "004020", "069960", "022100",
    "103590", "085620", "051900", "001450", "111770",
    "012510", "204320", "251270", "035250", "005850",
    "011170", "036460", "004800", "014680", "375500",
    "007810", "011780", "017800", "383220", "001720",
    "302440", "031210", "097950", "012750", "028670",
    "020150", "139130", "009420", "457190", "004990",
    "007340", "071970", "006360", "026960", "000240",
    "439260", "139480", "003690", "001740", "009970",
    "051600", "030000", "008770", "011210", "004370",
    "000155", "081660", "005440", "103140", "282330",
    "120110", "097230", "112610", "008930", "007070",
    "402340", "005935", "373220", "443060", "489790",
    "066970", "145020", "018260", "033780", "138040",
]
KOSPI200_CODES = list(dict.fromkeys(KOSPI200_CODES))

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
# 날짜 -> datetime 변환
# ---------------------------------------------------------------------------
def to_datetime(date_str: str) -> datetime:
    return datetime.strptime(date_str[:8], "%Y%m%d")


# ---------------------------------------------------------------------------
# mongodb 배치 upsert
# ---------------------------------------------------------------------------
def bulk_upsert(collection, docs: list, unique_keys: list):
    if not docs:
        return
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]
        ops = [
            UpdateOne({k: doc[k] for k in unique_keys}, {"$set": doc}, upsert=True)
            for doc in batch
        ]
        collection.bulk_write(ops, ordered=False)


# ---------------------------------------------------------------------------
# KIS 토큰 파일 저장/로드/재사용
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
# KIS 일봉 단일 페이지 수집 (종목명 포함)
# ---------------------------------------------------------------------------
def fetch_kis_daily_page(token: str, stock_code: str, start: str, end: str) -> tuple:
    """
    반환: (rows, stock_name)
    stock_name: output1 에서 추출한 종목명
    """
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
        "FID_INPUT_DATE_1": start,
        "FID_INPUT_DATE_2": end,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }
    res = rate_limited_get(url, headers, params)
    res.raise_for_status()
    data = res.json()

    if data.get("rt_cd") != "0":
        return [], None

    # output1 에서 종목명 추출
    stock_name = data.get("output1", {}).get("hts_kor_isnm", "")

    rows = []
    for item in data.get("output2", []):
        date_str = item.get("stck_bsop_date", "")
        if not date_str:
            continue
        rows.append({
            "stock_code": stock_code,
            "stock_name": stock_name,
            "date": to_datetime(date_str),
            "open": int(item.get("stck_oprc", 0) or 0),
            "high": int(item.get("stck_hgpr", 0) or 0),
            "low": int(item.get("stck_lwpr", 0) or 0),
            "close": int(item.get("stck_clpr", 0) or 0),
            "volume": int(item.get("acml_vol", 0) or 0),
            "trade_value": int(item.get("acml_tr_pbmn", 0) or 0),
            "interval": "1day",
            "source": "kis",
            "collected_at": datetime.now(),
        })
    return rows, stock_name


# ---------------------------------------------------------------------------
# 5년치 날짜 구간 리스트 생성
# ---------------------------------------------------------------------------
def build_date_ranges() -> list:
    ranges = []
    current_end  = datetime.strptime(END_DATE, "%Y%m%d")
    target_start = datetime.strptime(START_DATE, "%Y%m%d")

    while current_end >= target_start:
        current_start = max(current_end - timedelta(days=PAGE_DAYS), target_start)
        ranges.append((
            current_start.strftime("%Y%m%d"),
            current_end.strftime("%Y%m%d"),
        ))
        current_end = current_start - timedelta(days=1)

    return ranges


# ---------------------------------------------------------------------------
# 종목 1개 5년치 전체 수집 (500 오류 스킵)
# ---------------------------------------------------------------------------
def fetch_kis_daily_all(token: str, stock_code: str, date_ranges: list) -> list:
    all_rows   = []
    seen       = set()
    stock_name = ""

    for start, end in date_ranges:
        try:
            rows, name = fetch_kis_daily_page(token, stock_code, start, end)
            if name:
                stock_name = name
            for row in rows:
                key = row["date"]
                if key not in seen:
                    seen.add(key)
                    row["stock_name"] = stock_name
                    all_rows.append(row)
        except Exception as e:
            print(f"  [skip] {stock_code} {start}~{end} 오류: {e}")
            time.sleep(0.5)
            continue

    return all_rows


# ---------------------------------------------------------------------------
# 이미 수집된 종목 코드 조회 (resume)
# ---------------------------------------------------------------------------
def get_done_codes(collection) -> set:
    return set(collection.distinct("stock_code"))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print(f"[start] 코스피200 일봉 수집 (db: {DB_NAME})")
    print(f"[collection] {COLLECTION}")
    print(f"[period] {START_DATE} ~ {END_DATE} (5년치)")
    print(f"[config] 초당 20회 / {PAGE_DAYS}일씩 분할")

    db    = get_db()
    print("[mongo] 연결 완료")

    token = get_kis_token()

    date_ranges = build_date_ranges()
    print(f"[pages] 종목당 {len(date_ranges)}회 호출")
    print(f"[target] 코스피200 {len(KOSPI200_CODES)}개 종목")

    done_codes = get_done_codes(db[COLLECTION])
    remaining  = [c for c in KOSPI200_CODES if c not in done_codes]
    print(f"[resume] 완료 {len(done_codes)}개 / 남은 {len(remaining)}개")

    total_saved = 0
    for i, code in enumerate(remaining):
        try:
            rows = fetch_kis_daily_all(token, code, date_ranges)
            if rows:
                bulk_upsert(db[COLLECTION], rows, ["stock_code", "date"])
                total_saved += len(rows)
                name = rows[0].get("stock_name", "")
                print(f"[ohlcv] ({i+1}/{len(remaining)}) {code} {name} {len(rows)}건 저장 (누적: {total_saved})")
            else:
                print(f"[ohlcv] ({i+1}/{len(remaining)}) {code} 데이터 없음")
        except Exception as e:
            print(f"[ohlcv] ({i+1}/{len(remaining)}) {code} 오류: {e}")

    print(f"\n[done] 수집 완료 / 총 {total_saved}건 저장")


if __name__ == "__main__":
    main()
