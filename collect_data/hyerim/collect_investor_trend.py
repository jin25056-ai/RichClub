"""
investor_trend 수집
- 출처: pykrx
- 대상: KOSPI200 종목
- 기간: 5년치
- 저장: MongoDB Atlas > data_hyerim > investor_trend
- 함수: get_market_trading_value_by_date (종목별 투자자 거래대금)
"""

import os
import time
from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

# .env 파일 경로 명시적 지정
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path)

# 환경변수 확인
print(f'KRX_ID: {os.getenv("KRX_ID")}')
print(f'MONGO_URI: {"설정됨" if os.getenv("MONGO_URI") else "없음"}')

# MongoDB 연결
MONGO_URI = os.getenv('MONGO_URI')
client    = MongoClient(MONGO_URI)
db        = client['data_hyerim']
col       = db['investor_trend']

# 인덱스 생성
col.create_index([('stock_code', 1), ('date', 1)], unique=True)

# 날짜 설정
end_date   = datetime.today()
start_date = end_date - timedelta(days=365 * 5)
start_str  = start_date.strftime('%Y%m%d')
end_str    = end_date.strftime('%Y%m%d')

print(f'수집 기간: {start_str} ~ {end_str}')

# 종목 리스트 - MongoDB에서 가져옴
ohlcv_col = db['stock_ohlcv_kospi200']
raw_codes = ohlcv_col.distinct('stock_code')
tickers   = [str(c).zfill(6) for c in raw_codes]
print(f'대상 종목 수: {len(tickers)}개')

# 함수 테스트
print('\n함수 테스트 중...')
test_code = tickers[0]
try:
    test_df = stock.get_market_trading_value_by_date(
        start_str, end_str, test_code
    )
    print(f'테스트 성공: {test_df.shape}')
    print(f'컬럼: {test_df.columns.tolist()}')
    print(test_df.head(2))
except Exception as e:
    print(f'테스트 실패: {e}')
    client.close()
    exit()

# 수집
success    = 0
fail       = 0
total_docs = 0

for i, code in enumerate(tickers):
    try:
        # 종목별 투자자 거래대금 (순매수)
        df = stock.get_market_trading_value_by_date(
            start_str, end_str, code
        )

        if df is None or len(df) == 0:
            print(f'[{i+1}/{len(tickers)}] {code} - 데이터 없음')
            fail += 1
            continue

        df = df.reset_index()

        # 날짜 컬럼
        date_col = df.columns[0]
        df = df.rename(columns={date_col: 'date'})
        df['date'] = pd.to_datetime(df['date'])

        # 컬럼 매핑
        rename_map = {}
        for c in df.columns:
            c_str = str(c)
            if '개인' in c_str:
                rename_map[c] = 'individual'
            elif '외국인합계' in c_str or c_str == '외국인':
                rename_map[c] = 'foreign'
            elif '기관합계' in c_str or c_str == '기관':
                rename_map[c] = 'institution'

        df = df.rename(columns=rename_map)

        # MongoDB upsert
        ops = []
        for _, row in df.iterrows():
            doc = {
                'stock_code':   code,
                'date':         row['date'].to_pydatetime(),
                'collected_at': datetime.now(),
            }
            for col_name in ['individual', 'foreign', 'institution']:
                if col_name in row and pd.notna(row[col_name]):
                    doc[col_name] = int(row[col_name])

            ops.append(UpdateOne(
                {'stock_code': code, 'date': doc['date']},
                {'$set': doc},
                upsert=True
            ))

        if ops:
            col.bulk_write(ops, ordered=False)
            total_docs += len(ops)

        success += 1
        print(f'[{i+1}/{len(tickers)}] {code} 완료 ({len(df)}건)')

        time.sleep(0.3)

    except Exception as e:
        fail += 1
        print(f'[{i+1}/{len(tickers)}] {code} 실패: {e}')
        time.sleep(1)

print(f'\n=== 수집 완료 ===')
print(f'성공: {success}개')
print(f'실패: {fail}개')
print(f'총 저장: {total_docs:,}건')
client.close()
