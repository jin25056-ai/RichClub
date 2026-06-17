"""
collect_basic.py
pykrx + yfinance + 한국투자증권 REST API 기본 데이터 수집
"""

import os
import time
import requests
import pandas as pd
import yfinance as yf
from pykrx import stock
from datetime import datetime, timedelta
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
from io import StringIO

load_dotenv()

# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------
KIS_APP_KEY    = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_BASE_URL   = os.getenv("KIS_BASE_URL")

MONGO_URI      = os.getenv("MONGO_URI")
DB_NAME        = os.getenv("MONGO_DB_NAME", "data_hyerim")

BATCH_SIZE = 200

today      = datetime.today()
END_DATE   = (today - timedelta(days=1)).strftime("%Y%m%d")
START_DATE = (today - timedelta(days=365 * 5)).strftime("%Y%m%d")
YF_START   = (today - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
END_DT     = datetime.strptime(END_DATE, "%Y%m%d").strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# mongodb 연결
# ---------------------------------------------------------------------------
def get_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return client[DB_NAME]


# ---------------------------------------------------------------------------
# 날짜 -> datetime 변환 (MongoDB에 datetime으로 저장)
# ---------------------------------------------------------------------------
def to_datetime(val) -> datetime:
    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)
    if isinstance(val, datetime):
        return val.replace(hour=0, minute=0, second=0, microsecond=0)
    if isinstance(val, pd.Series):
        val = val.iloc[0]
    # 문자열 처리 ("20230620" or "2023-06-20")
    s = str(val)[:10].replace("-", "")
    return datetime.strptime(s[:8], "%Y%m%d")


# ---------------------------------------------------------------------------
# mongodb 배치 upsert
# ---------------------------------------------------------------------------
def bulk_upsert(collection, docs: list, unique_keys: list):
    if not docs:
        return
    total = 0
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]
        ops = [
            UpdateOne({k: doc[k] for k in unique_keys}, {"$set": doc}, upsert=True)
            for doc in batch
        ]
        collection.bulk_write(ops, ordered=False)
        total += len(batch)
        print(f"  [mongo] {collection.name} {total}/{len(docs)}건 저장", end="\r")
    print(f"  [mongo] {collection.name} {len(docs)}건 저장 완료        ")


# ---------------------------------------------------------------------------
# yfinance 단일 ticker 수집
# ---------------------------------------------------------------------------
def fetch_yfinance(name: str, ticker: str, start: str, end: str) -> list:
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            print(f"[yfinance] {name} 데이터 없음")
            return []

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        df = df.reset_index()
        rows = []
        for _, row in df.iterrows():
            date_val = row.get("Date") or row.get("Datetime") or row.iloc[0]
            rows.append({
                "indicator": name,
                "date": to_datetime(date_val),
                "open": float(row.get("Open", 0) or 0),
                "high": float(row.get("High", 0) or 0),
                "low": float(row.get("Low", 0) or 0),
                "close": float(row.get("Close", 0) or 0),
                "volume": float(row.get("Volume", 0) or 0),
                "collected_at": datetime.now(),
            })
        print(f"[yfinance] {name} {len(rows)}건 수집 완료")
        return rows
    except Exception as e:
        print(f"[yfinance] {name} 실패: {e}")
        return []


# ---------------------------------------------------------------------------
# 글로벌 + 국내 지수 수집
# ---------------------------------------------------------------------------
def collect_market_indicators(db):
    tickers = {
        "nasdaq":    "^IXIC",
        "sp500":     "^GSPC",
        "dow":       "^DJI",
        "vix":       "^VIX",
        "wti":       "CL=F",
        "gold":      "GC=F",
        "usd_krw":   "KRW=X",
        "usd_index": "DX-Y.NYB",
        "kospi":     "^KS11",
        "kosdaq":    "^KQ11",
    }

    for name, ticker in tickers.items():
        rows = fetch_yfinance(name, ticker, YF_START, END_DT)
        if rows:
            bulk_upsert(db["market_indicators"], rows, ["indicator", "date"])


# ---------------------------------------------------------------------------
# 전종목 코드 조회
# ---------------------------------------------------------------------------
def get_all_stock_codes_from_krx() -> list:
    # 방법 1: KRX OTP
    try:
        otp_url = "http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd"
        otp_params = {
            "locale": "ko_KR",
            "mktId": "ALL",
            "trdDd": END_DATE,
            "share": "1",
            "money": "1",
            "csvxls_isNo": "false",
            "name": "fileDown",
            "url": "dbms/MDC/STAT/standard/MDCSTAT01901",
        }
        headers = {
            "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020101",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        otp_res = requests.post(otp_url, params=otp_params, headers=headers, timeout=15)
        otp = otp_res.text.strip()
        down_url = "http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd"
        down_res = requests.post(down_url, data={"code": otp}, headers=headers, timeout=15)
        down_res.encoding = "euc-kr"
        df = pd.read_csv(StringIO(down_res.text))
        if not df.empty and len(df.columns) > 0:
            codes = df.iloc[:, 0].astype(str).str.zfill(6).tolist()
            if len(codes) > 100:
                print(f"[krx] 전종목 {len(codes)}개 조회 완료 (OTP)")
                return codes
    except Exception as e:
        print(f"[krx] OTP 방식 실패: {e}")

    # 방법 2: FinanceDataReader
    try:
        import FinanceDataReader as fdr
        df_kospi  = fdr.StockListing("KOSPI")
        df_kosdaq = fdr.StockListing("KOSDAQ")
        codes = df_kospi["Code"].tolist() + df_kosdaq["Code"].tolist()
        codes = [str(c).zfill(6) for c in codes]
        print(f"[fdr] 전종목 {len(codes)}개 조회 완료")
        return codes
    except Exception as e:
        print(f"[fdr] 방식 실패: {e}")

    # 방법 3: pykrx
    try:
        yesterday = (today - timedelta(days=1)).strftime("%Y%m%d")
        kospi  = list(stock.get_market_ticker_list(yesterday, market="KOSPI"))
        kosdaq = list(stock.get_market_ticker_list(yesterday, market="KOSDAQ"))
        if kospi:
            codes = kospi + kosdaq
            print(f"[pykrx] 전종목 {len(codes)}개 조회 완료")
            return codes
    except Exception as e:
        print(f"[pykrx] 방식 실패: {e}")

    return []


# ---------------------------------------------------------------------------
# 한국투자증권 access token 발급
# ---------------------------------------------------------------------------
def get_kis_token() -> str:
    url = f"{KIS_BASE_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
    }
    res = requests.post(url, headers=headers, json=body, timeout=10)
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
    res = requests.get(url, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    data = res.json()
    rows = []
    for item in data.get("output2", []):
        rows.append({
            "stock_code": stock_code,
            "date": to_datetime(item.get("stck_bsop_date")),
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
# pykrx 일봉 OHLCV 수집
# ---------------------------------------------------------------------------
def fetch_pykrx_ohlcv_daily(stock_code: str, start: str, end: str) -> list:
    try:
        df = stock.get_market_ohlcv_by_date(start, end, stock_code)
        if df is None or df.empty:
            return []
        df = df.reset_index()
        date_col = df.columns[0]
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "stock_code": stock_code,
                "date": to_datetime(row[date_col]),
                "open": int(row.get("시가", 0)),
                "high": int(row.get("고가", 0)),
                "low": int(row.get("저가", 0)),
                "close": int(row.get("종가", 0)),
                "volume": int(row.get("거래량", 0)),
                "source": "pykrx",
                "collected_at": datetime.now(),
            })
        return rows
    except Exception as e:
        print(f"[pykrx] ohlcv 실패 {stock_code}: {e}")
        return []


# ---------------------------------------------------------------------------
# pykrx 외국인/기관 수급 수집
# ---------------------------------------------------------------------------
def fetch_investor_trend(stock_code: str, start: str, end: str) -> list:
    try:
        df = stock.get_market_trading_value_by_date(start, end, stock_code)
        if df is None or df.empty:
            return []
        df = df.reset_index()
        df.columns = [c.strip() for c in df.columns]
        date_col = df.columns[0]
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "stock_code": stock_code,
                "date": to_datetime(row[date_col]),
                "individual": int(row.get("개인", 0)),
                "foreign": int(row.get("외국인", 0)),
                "institution": int(row.get("기관합계", 0)),
                "collected_at": datetime.now(),
            })
        return rows
    except Exception as e:
        print(f"[pykrx] 수급 실패 {stock_code}: {e}")
        return []


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print(f"[start] 데이터 수집 시작 (db: {DB_NAME})")
    print(f"[period] {START_DATE} ~ {END_DATE} / 글로벌지표 10년치")
    db = get_db()
    print("[mongo] 연결 완료")

    # 1. 시장 지표 전체
    print("\n[step] 시장 지표 수집")
    collect_market_indicators(db)

    # 2. 전종목 코드 조회
    print("\n[step] 전종목 코드 조회")
    all_codes = get_all_stock_codes_from_krx()

    if not all_codes:
        print("[warn] 종목 리스트 조회 실패")
    else:
        # 3. OHLCV 수집
        print(f"\n[step] OHLCV 수집 ({len(all_codes)}개 종목, 5년치)")
        kis_token = None
        try:
            kis_token = get_kis_token()
        except Exception as e:
            print(f"[kis] token 실패, pykrx로만 수집: {e}")

        for i, code in enumerate(all_codes):
            rows = []
            if kis_token:
                try:
                    rows = fetch_kis_ohlcv_daily(kis_token, code, START_DATE, END_DATE)
                except Exception:
                    pass
            if not rows:
                rows = fetch_pykrx_ohlcv_daily(code, START_DATE, END_DATE)

            if rows:
                bulk_upsert(db["stock_ohlcv"], rows, ["stock_code", "date"])
                print(f"[ohlcv] ({i+1}/{len(all_codes)}) {code} {len(rows)}건 저장")
            else:
                print(f"[ohlcv] ({i+1}/{len(all_codes)}) {code} 데이터 없음")
            time.sleep(0.3)

        # 4. 수급 수집
        print(f"\n[step] 수급 수집 ({len(all_codes)}개 종목)")
        for i, code in enumerate(all_codes):
            rows = fetch_investor_trend(code, START_DATE, END_DATE)
            if rows:
                bulk_upsert(db["investor_trend"], rows, ["stock_code", "date"])
                print(f"[trend] ({i+1}/{len(all_codes)}) {code} {len(rows)}건 저장")
            time.sleep(0.3)

    print("\n[done] 전체 수집 완료")


if __name__ == "__main__":
    main()
