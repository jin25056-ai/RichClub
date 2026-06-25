import pandas as pd
import numpy as np
import os
import joblib
import matplotlib.pyplot as plt
import seaborn as sns
from tensorflow.keras.models import load_model
from pymongo import MongoClient

# ===== 1. 경로 설정 =====
base_dir = os.path.dirname(os.path.abspath(__file__))
model_dir = os.path.normpath(os.path.join(base_dir, "..", "..", "model","seongsu"))  # 학습 스크립트와 동일한 경로로 맞추기

# ===== 2. 모델 / scaler / threshold 로드 =====
model = load_model(os.path.join(model_dir, "lstm_anomaly_model.keras"))
scalers = joblib.load(os.path.join(model_dir, "scaler.pkl"))
threshold = joblib.load(os.path.join(model_dir, "threshold.pkl"))

feature_cols = ['return', 'high_low_ratio', 'open_close_ratio',
                 'foreign_ratio', 'individual_ratio', 'institution_ratio',
                 'log_trade_value', 'log_volume']
window = 30

# ===== 3. 신규(테스트) 데이터 로드 =====
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['data_hyerim']
inv = db['investor_trend']
inv = pd.DataFrame(inv.find())
ohlcv = db['stock_ohlcv_kospi200']
ohlcv = pd.DataFrame(ohlcv.find())

df = pd.merge(inv,ohlcv,on=['stock_code','date'])
df = df[['stock_name','stock_code', 'date',  'foreign',
       'individual', 'institution', 'close', 'high',
       'low', 'open', 'trade_value', 'volume'
       ]]

df = df.sort_values(['stock_code', 'date'])

# ===== 4. 학습 때와 동일한 피처 생성 =====
df['return'] = df.groupby('stock_code')['close'].pct_change()
df['high_low_ratio'] = (df['high'] - df['low']) / df['close']
df['open_close_ratio'] = (df['close'] - df['open']) / df['open']

for col in ['foreign', 'individual', 'institution']:
    df[f'{col}_ratio'] = df[col] / df['trade_value'].replace(0, np.nan)

df['log_trade_value'] = np.log1p(df['trade_value'])
df['log_volume'] = np.log1p(df['volume'])

# ===== 5. 학습 때 저장한 scaler로 transform만 적용 (fit 없음) =====
for col in feature_cols:
    df[col] = scalers[col].transform(df[[col]])

df = df.dropna(subset=feature_cols)

# ===== 6. 시퀀스 생성 (종목 경계 안 넘도록) =====
def make_sequences(df, feature_cols, window=30):
    X, meta = [], []
    for code, group in df.groupby('stock_code'):
        group = group.sort_values('date')
        values = group[feature_cols].values
        name = group['stock_name'].iloc[0]
        if len(values) <= window:
            continue
        for i in range(len(values) - window):
            X.append(values[i:i+window])
            meta.append((code, name, group['date'].iloc[i+window]))
    return np.array(X), meta

X_test, meta_test = make_sequences(df, feature_cols, window=window)

# ===== 7. 예측 & 재구성 오차 계산 =====
reconstructed = model.predict(X_test)
error = np.mean((X_test - reconstructed) ** 2, axis=(1, 2))

result_df = pd.DataFrame(meta_test, columns=['stock_code', 'stock_name', 'date'])
result_df['error'] = error

# ===== 8. 종목별 집계 & 이상 종목 판별 =====
stock_score = result_df.groupby(['stock_code', 'stock_name'])['error'].mean().sort_values(ascending=False)
anomalous_stocks = stock_score[stock_score > threshold]
print(anomalous_stocks)

# ===== 9. 시각화 - 정상/이상 분포 =====
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# ===== 10. 시각화 - Top 이상 종목 =====
top_n = 15
top_anomalies = stock_score.head(top_n)

plt.figure(figsize=(10, 6))
colors = ['tomato' if v > threshold else 'steelblue' for v in top_anomalies.values][::-1]
top_anomalies.sort_values().plot(kind='barh', color=colors)
plt.axvline(threshold, color='black', linestyle='--', label=f'Threshold ({threshold:.4f})')
plt.xlabel('Mean Reconstruction Error')
plt.title('Test Data: Top Anomalous Stocks')
plt.legend()
plt.tight_layout()
plt.show()