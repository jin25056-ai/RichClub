"""
collect_basic.py
한국투자증권 REST API + pykrx + yfinance 기본 데이터 수집
"""

import os
import time
import requests
import pandas as pd
import yfinance as yf
from pykrx import stock
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------
KIS_APP_KEY    = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_BASE_URL   = os.getenv("KIS_BASE_URL")

MONGO_URI      = os.getenv("MONGO_URI")
DB_NAME        = os.getenv("MONGO_DB_NAME", "data_hyerim")

STOCK_CODES = ["005930", "000660", "035420", "051910", "005380"]
# 삼성전자, SK하이닉스, NAVER, LG화학, 현대차

END_DATE   = datetime.today().strftime("%Y%m%d")
START_DATE = (datetime.today() - timedelta(days=365 * 3)).strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# mongodb 연결
# ---------------------------------------------------------------------------
def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]


# ---------------------------------------------------------------------------
# 한국투자증권 access token 발급
# ---------------------------------------------------------------------------
def get_kis_token():
    url = f"{KIS_BASE_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
    }
    res = requests.post(url, headers=headers, json=body)
    res.raise_for_status()
    token = res.json().get("access_token")
    print("[kis] token 발급 완료")
    return token


# ---------------------------------------------------------------------------
# 한국투자증권 일봉 OHLCV 수집
# ---------------------------------------------------------------------------
def fetch_kis_ohlcv_daily(token: str, stock_code: str, start: str, end: str) -> list:
    url = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "FHKST03010100",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": start,
        "FID_INPUT_DATE_2": end,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }
    res = requests.get(url, headers=headers, params=params)
    res.raise_for_status()
    data = res.json()

    rows = []
    for item in data.get("output2", []):
        rows.append({
            "stock_code": stock_code,
            "date": item.get("stck_bsop_date"),
            "open": int(item.get("stck_oprc", 0)),
            "high": int(item.get("stck_hgpr", 0)),
            "low": int(item.get("stck_lwpr", 0)),
            "close": int(item.get("stck_clpr", 0)),
            "volume": int(item.get("acml_vol", 0)),
            "source": "kis",
            "collected_at": datetime.now(),
        })
    return rows


# ---------------------------------------------------------------------------
# pykrx 외국인/기관 수급 수집
# ---------------------------------------------------------------------------
def fetch_investor_trend(stock_code: str, start: str, end: str) -> list:
    try:
        df = stock.get_market_trading_value_by_date(start, end, stock_code)
        df = df.reset_index()
        df.columns = [c.strip() for c in df.columns]

        rows = []
        for _, row in df.iterrows():
            rows.append({
                "stock_code": stock_code,
                "date": row["날짜"].strftime("%Y%m%d") if hasattr(row["날짜"], "strftime") else str(row["날짜"]),
                "individual": int(row.get("개인", 0)),
                "foreign": int(row.get("외국인", 0)),
                "institution": int(row.get("기관합계", 0)),
                "collected_at": datetime.now(),
            })
        return rows
    except Exception as e:
        print(f"[pykrx] 수급 수집 실패 {stock_code}: {e}")
        return []


# ---------------------------------------------------------------------------
# yfinance 글로벌 지수 + 유가 수집
# ---------------------------------------------------------------------------
def fetch_global_indicators(start: str, end: str) -> list:
    tickers = {
        "nasdaq":  "^IXIC",
        "sp500":   "^GSPC",
        "wti":     "CL=F",
        "usd_krw": "KRW=X",
    }

    start_dt = datetime.strptime(start, "%Y%m%d").strftime("%Y-%m-%d")
    end_dt   = datetime.strptime(end,   "%Y%m%d").strftime("%Y-%m-%d")

    rows = []
    for name, ticker in tickers.items():
        try:
            df = yf.download(ticker, start=start_dt, end=end_dt, progress=False)
            df = df.reset_index()
            for _, row in df.iterrows():
                rows.append({
                    "indicator": name,
                    "date": row["Date"].strftime("%Y%m%d"),
                    "open": float(row.get("Open", 0)),
                    "high": float(row.get("High", 0)),
                    "low": float(row.get("Low", 0)),
                    "close": float(row.get("Close", 0)),
                    "volume": float(row.get("Volume", 0)),
                    "collected_at": datetime.now(),
                })
            print(f"[yfinance] {name} {len(df)}건 수집 완료")
        except Exception as e:
            print(f"[yfinance] {name} 수집 실패: {e}")

    return rows


# ---------------------------------------------------------------------------
# pykrx 코스피/코스닥 지수 수집
# ---------------------------------------------------------------------------
def fetch_krx_index(start: str, end: str) -> list:
    indices = {
        "kospi":  "1028",
        "kosdaq": "2001",
    }
    rows = []
    for name, ticker in indices.items():
        try:
            df = stock.get_index_ohlcv_by_date(start, end, ticker)
            df = df.reset_index()
            for _, row in df.iterrows():
                rows.append({
                    "indicator": name,
                    "date": row["날짜"].strftime("%Y%m%d") if hasattr(row["날짜"], "strftime") else str(row["날짜"]),
                    "open": float(row.get("시가", 0)),
                    "high": float(row.get("고가", 0)),
                    "low": float(row.get("저가", 0)),
                    "close": float(row.get("종가", 0)),
                    "volume": float(row.get("거래량", 0)),
                    "collected_at": datetime.now(),
                })
            print(f"[pykrx] {name} {len(df)}건 수집 완료")
        except Exception as e:
            print(f"[pykrx] {name} 수집 실패: {e}")
    return rows


# ---------------------------------------------------------------------------
# mongodb upsert 공통 함수
# ---------------------------------------------------------------------------
def upsert_many(collection, docs: list, unique_keys: list):
    if not docs:
        return
    for doc in docs:
        filter_query = {k: doc[k] for k in unique_keys}
        collection.update_one(filter_query, {"$set": doc}, upsert=True)
    print(f"[mongo] {collection.name} {len(docs)}건 저장 완료")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print(f"[start] 데이터 수집 시작 (db: {DB_NAME})")
    db = get_db()
    print("[mongo] 연결 완료")

    # 1. 한국투자증권 일봉 OHLCV
    try:
        token = get_kis_token()
        for code in STOCK_CODES:
            rows = fetch_kis_ohlcv_daily(token, code, START_DATE, END_DATE)
            upsert_many(db["stock_ohlcv"], rows, ["stock_code", "date"])
            print(f"[kis] {code} {len(rows)}건 저장")
            time.sleep(0.5)
    except Exception as e:
        print(f"[kis] 오류: {e}")

    # 2. pykrx 외국인/기관 수급
    for code in STOCK_CODES:
        rows = fetch_investor_trend(code, START_DATE, END_DATE)
        upsert_many(db["investor_trend"], rows, ["stock_code", "date"])
        time.sleep(0.3)

    # 3. yfinance 글로벌 지수 + 유가 + 환율
    rows = fetch_global_indicators(START_DATE, END_DATE)
    upsert_many(db["market_indicators"], rows, ["indicator", "date"])

    # 4. pykrx 코스피/코스닥
    rows = fetch_krx_index(START_DATE, END_DATE)
    upsert_many(db["market_indicators"], rows, ["indicator", "date"])

    print("\n[done] 수집 완료")


if __name__ == "__main__":
    main()
