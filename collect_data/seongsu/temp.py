from pymongo import MongoClient
import requests  
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI  = os.getenv("MONGO_URI")
API_KEY    = os.getenv("API_KEY")

api_server =     'https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/' 
service_type = 'getStockPriceInfo?'
numofrow = 'numOfRows=10000&'
pg_no = '&pageNo='
result_type = 'resultType=json&'
start_date = '20220101'
API_SERVER = api_server + service_type + API_KEY + numofrow + result_type + pg_no

client =MongoClient(MONGO_URI) 
db = client['data_seongsu']
collection = db['stock_data']
dataset = []
try:
    for i in range(1,303,1):
        host = f'{API_SERVER}{i}&beginBasDt={start_date}'
        print(host)
        response = requests.get(host)
        result = response.json()['response']['body']['items']['item']
        for data in result:
            dataset.append({
                    'date'          : data['basDt'],
                    'name'          : data['itmsNm'],
                    'end'           : data['clpr'],
                    'vs'            : data['vs'],
                    'fltRt'         : data['fltRt'],
                    'mkp'           : data['mkp'],
                    'high'          : data['hipr'],
                    'low'           : data['lopr'],
                    'trqu'          : data['trqu'],
                    'trPrc'         : data['trPrc'],
                    'lstgStCnt'     : data['lstgStCnt'],
                    'mrktTotAmt'    : data['mrktTotAmt']
                })
        df = pd.DataFrame(dataset)
        collection.insert_many(df.to_dict('records'))
        dataset = []
except requests.exceptions.RequestException as e:
    print(f" 서버 연결 오류: {e}\n")
'''
{
'basDt': '20260616',        기준 일자
'srtnCd': '900260',         단축코드
'isinCd': 'HK0000295359',   isn코드
'itmsNm': '로스웰',           종목명
'mrktCtg': 'KOSDAQ',        시장구분
'clpr': '1631',             종가
'vs': '-39',                대비
fltRt': '-2.34',            등락률
'mkp': '1670',              시가
'hipr': '1693',             고가
'lopr': '1631',             저가
'trqu': '37849',            거래량
'trPrc': '62424805',        거래대금
'lstgStCnt': '46029706',    상장주식수
'mrktTotAmt': '75074450486' 시가총액
}
'''