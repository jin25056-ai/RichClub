from pymongo import MongoClient
import requests  
import pandas as pd
from dotenv import load_dotenv
import os
import kospi_200_data as kospi200

from sklearn.preprocessing import LabelEncoder

le = LabelEncoder()

load_dotenv()
MONGO_URI  = os.getenv("MONGO_URI")
API_KEY    = os.getenv("API_KEY")

api_server =     'https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/' 
service_type = 'getStockPriceInfo?'
numofrow = 'numOfRows=10000&'
pg_no = '&pageNo='
result_type = 'resultType=json&'
start_date = '20211116'
stock_type = 'mrktCls=KOSPI'
API_SERVER = api_server + service_type + API_KEY + numofrow + result_type + pg_no

client =MongoClient(MONGO_URI) 
db = client['data_seongsoo']
collection = db['stock_data']
dataset = []
try:
    for i in range(1,300,1):
        host = f'{API_SERVER}{i}&beginBasDt={start_date}&{stock_type}'
        print(host)
        response = requests.get(host)
        result = response.json()['response']['body']['items']['item']
        df = pd.DataFrame(result)
        ksp200 = df[df['itmsNm'].isin(kospi200.kospi_200)].drop(
            columns=["srtnCd",'isinCd','mrktCtg']
            )
        
        ksp200['기준일자'] = pd.to_datetime(ksp200['basDt'])           #기준일자
        ksp200['종가'] = pd.to_numeric(ksp200['clpr'])              #종가
        ksp200['대비'] = pd.to_numeric(ksp200['vs'])                  #대비
        ksp200['등락률'] = pd.to_numeric(ksp200['fltRt'])            #등락률
        ksp200['시가'] = pd.to_numeric(ksp200['mkp'])                #시가
        ksp200['고가'] = pd.to_numeric(ksp200['hipr'])              #고가
        ksp200['저가'] = pd.to_numeric(ksp200['lopr'])              #저가
        ksp200['거래량'] = pd.to_numeric(ksp200['trqu'])             #거래량
        ksp200['거래대금'] = pd.to_numeric(ksp200['trPrc'])          #거래대금
        ksp200['상장주식수'] = pd.to_numeric(ksp200['lstgStCnt'])    #상장주식수
        ksp200['시가총액'] = pd.to_numeric(ksp200['mrktTotAmt'])    #시가총액
        # ksp200['종가변화율'] = ksp200['종가'].pct_change()
        # ksp200['거래량변화율'] = ksp200['거래량'].pct_change()
        # ksp200['시총변화율'] = ksp200['시가총액'].pct_change()
        # ksp200['몸통'] = (ksp200['종가'] - ksp200['시가']) / ksp200['시가']
        # ksp200['윗꼬리'] = (ksp200['고가'] - ksp200[['종가','시가']].max(axis=1)) / ksp200['시가']
        # ksp200['아랫꼬리'] = (ksp200[['종가','시가']].min(axis=1) - ksp200['저가']) / ksp200['시가']

        # for p in [5, 20, 60]:
        #     ksp200[f'ma_{p}'] = ksp200['종가'].rolling(p).mean()

        # ksp200['ma5_gap'] = ksp200['종가'] / ksp200['ma_5']
        # ksp200['ma20_gap'] = ksp200['종가'] / ksp200['ma_20']

        # ksp200['종목코드'] = le.fit_transform(ksp200['itmsNm'])
        ksp200.drop(columns=['basDt','clpr','vs','fltRt','mkp','hipr','lopr','trqu','trPrc','lstgStCnt','mrktTotAmt'] , inplace=True)
        # print(ksp200)
        collection.insert_many(ksp200.to_dict('records'))
except requests.exceptions.RequestException as e:
    print(f" 서버 연결 오류: {e}\n")