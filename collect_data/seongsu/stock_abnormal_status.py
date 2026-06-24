import pandas as pd
import numpy as np
import tensorflow as tf
import os
import joblib
import matplotlib.pyplot as plt

from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.preprocessing import LabelEncoder
# from sklearn.preprocessing import StandardScaler
# from tensorflow.keras.models import Sequential
# from tensorflow.keras.layers import LSTM, Dense , RepeatVector, TimeDistributed

from sklearn.model_selection import train_test_split
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, LSTM, RepeatVector, TimeDistributed, Dense
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau

le = LabelEncoder()

# MONGO_URI = os.getenv("MONGO_URI")
# client = MongoClient(MONGO_URI)
# client =MongoClient(MONGO_URI) 
# db = client['data_hyerim']
# inv = db['investor_trend']
# ohlcv = db['stock_ohlcv_kospi200']
# print('db 연결 완료')
# print(inv)
# inv = pd.DataFrame(inv.find())
# ohlcv = pd.DataFrame(ohlcv.find())
base_dir = os.path.dirname(os.path.abspath(__file__))
file_path_inv = os.path.join(base_dir, "investor_trend.csv")
inv = pd.read_csv(file_path_inv)
file_path_ohlcv = os.path.join(base_dir, "stock_ohlcv_kospi200.csv")
ohlcv = pd.read_csv(file_path_ohlcv)

df = pd.merge(inv,ohlcv,on=['stock_code','date'])
df = df[[
    'stock_name','stock_code','date','foreign','individual','institution','close','high','low','open','volume','trade_value'
    ]]
# df = df.sort_values(['date']).reset_index(drop=True)

# df = df.sort_values(['stock_code', 'date'])

# 가격: 수익률로 변환 (비정상성 완화)
df['return'] = df.groupby('stock_code')['close'].pct_change()
df['high_low_ratio'] = (df['high'] - df['low']) / df['close']
df['open_close_ratio'] = (df['close'] - df['open']) / df['open']

# 수급: 거래량 대비 비율로 정규화 (종목별 규모 차이 제거)
for col in ['foreign', 'individual', 'institution']:
    df[f'{col}_ratio'] = df[col] / df['trade_value'].replace(0, np.nan)

# 거래: 로그 변환 후 종목별 z-score
df['log_trade_value'] = np.log1p(df['trade_value'])
df['log_volume'] = np.log1p(df['volume'])

feature_cols = ['return', 'high_low_ratio', 'open_close_ratio',
                 'foreign_ratio', 'individual_ratio', 'institution_ratio',
                 'log_trade_value', 'log_volume']

df[feature_cols] = df.groupby('stock_code')[feature_cols].transform(
    lambda x: (x - x.mean()) / (x.std() + 1e-8)
)

df = df.dropna(subset=feature_cols)

def make_sequences(df, window=30):
    X, meta = [], []
    for code, group in df.groupby('stock_code'):
        group = group.sort_values('date')
        values = group[feature_cols].values
        name = group['stock_name'].iloc[0]
        for i in range(len(values) - window):
            X.append(values[i:i+window])
            meta.append((code, name, group['date'].iloc[i+window]))
    return np.array(X), meta

X, meta = make_sequences(df, window=30)


timesteps, n_features = X.shape[1], X.shape[2]

inputs = Input(shape=(timesteps, n_features))
encoded = LSTM(64, activation='tanh', return_sequences=True)(inputs)
encoded = LSTM(32, activation='tanh', return_sequences=False)(encoded)
decoded = RepeatVector(timesteps)(encoded)
decoded = LSTM(32, activation='tanh', return_sequences=True)(decoded)
decoded = LSTM(64, activation='tanh', return_sequences=True)(decoded)
outputs = TimeDistributed(Dense(n_features))(decoded)

model = Model(inputs, outputs)
model.compile(optimizer='adam', loss='mse')


X_train, X_val = train_test_split(X, test_size=0.1, shuffle=True, random_state=42)

callbacks = [
    EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True),
    ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3)
]

model.fit(X_train, X_train,
          validation_data=(X_val, X_val),
          epochs=50,
          batch_size=128,
          shuffle=True,
          callbacks=callbacks)

reconstructed = model.predict(X)
error = np.mean((X - reconstructed) ** 2, axis=(1, 2))

result_df = pd.DataFrame(meta, columns=['stock_code', 'stock_name', 'date'])
result_df['error'] = error

stock_score = result_df.groupby(['stock_code', 'stock_name'])['error'].mean().sort_values(ascending=False)
threshold = stock_score.mean() + 2 * stock_score.std()
anomalous_stocks = stock_score[stock_score > threshold]
print(anomalous_stocks)
import seaborn as sns

is_anomaly = error > threshold

plt.figure(figsize=(10, 5))
sns.kdeplot(error[~is_anomaly], label='Normal', fill=True, color='steelblue')
sns.kdeplot(error[is_anomaly], label='Anomaly', fill=True, color='tomato')
plt.axvline(threshold, color='black', linestyle='--', label='Threshold')
plt.xlabel('Reconstruction Error')
plt.title('Error Distribution: Normal vs Anomaly')
plt.legend()
plt.tight_layout()
plt.show()

model.save("/Users/inainz/workspace/RichClub/model/seongsu/lstm_anomaly_model.keras")
# joblib.dump(scaler, "/Users/inainz/workspace/RichClub//model/seongsu/scaler.pkl")
joblib.dump(threshold, "/Users/inainz/workspace/RichClub//model/seongsu/threshold.pkl")