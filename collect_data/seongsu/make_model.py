from pymongo import MongoClient
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import os

# 시각화
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc

# ① 폰트 설정
plt.rcParams['font.family'] = 'Malgun Gothic'  # 한글 폰트 지정
plt.rcParams['axes.unicode_minus'] = False     # 마이너스 부호 깨짐 방지

load_dotenv()
MONGO_URI  = os.getenv("MONGO_URI")
client =MongoClient(MONGO_URI) 
db = client['data_seongsoo']
collection = db['stock_data']

df = pd.DataFrame(collection.find({'itmsNm':'삼성전자'})).sort_values(by=['itmsNm','기준일자'],axis=0)

# 'date' 컬럼을 datetime 형식으로 변환
df['기준일자'] = pd.to_datetime(df['기준일자'])

# 중심선 (SMA)
#볼린저 밴드의 이동평균선
df['bb_mid'] = df['종가'].rolling(window=18).mean()

# 표준편차
df['bb_std'] = df['종가'].rolling(window=18).std()

# 상단/하단 밴드
df['bb_upper'] = df['bb_mid'] + (2 * df['bb_std'])
df['bb_lower'] = df['bb_mid'] - (2 * df['bb_std'])


df['obv'] = (np.sign(df['종가'].diff()) * df['거래량']).fillna(0).cumsum()
df['obv_diff9'] = df['obv'].diff(9)

# 시각화
# 그래프 크기 및 스타일 설정
plt.figure(figsize=(15, 5))

# # 선 그래프 생성
plt.plot(df['기준일자'], df['종가'], color='red' , label='상단선')
plt.plot(df['기준일자'], df['bb_upper'], color='blue', linestyle='-', label='상단선')
plt.plot(df['기준일자'], df['bb_mid'], color='black', linestyle='-', label='볼린저밴드 이동평균선')
# plt.plot(df['기준일자'], df['obv'], color='green', linestyle='-', label='obv')
# plt.plot(df['기준일자'], df['obv_diff9'], color='yellow', linestyle='-', label='obv_diff9')
plt.plot(df['기준일자'], df['bb_lower'], color='blue', linestyle='-', label='하단선')
plt.title('삼성전자 주식 일봉', fontsize=14)
plt.xlabel('일', fontsize=12)
plt.ylabel('주가', fontsize=12)
plt.grid(True)
plt.legend()

# X축 눈금 라벨 회전
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()