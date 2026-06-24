import pandas as pd
import numpy as np
import tensorflow as tf
import os
import joblib

from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.preprocessing import LabelEncoder
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense , RepeatVector, TimeDistributed

le = LabelEncoder()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
client =MongoClient(MONGO_URI) 
db = client['data_hyerim']
inv = db['investor_trend']
ohlcv = db['stock_ohlcv_kospi200']
print('db 연결 완료')
# print(inv)
inv = pd.DataFrame(inv.find())
ohlcv = pd.DataFrame(ohlcv.find())

df = pd.merge(inv,ohlcv,on=['stock_code','date'])
df = df[[
    'stock_name','date','foreign','individual','institution','close','high','low','open','volume','trade_value'
    ]]
df = df.sort_values(['date']).reset_index(drop=True)

FEATURE_COLUMNS = ['open', 'high', 'low', 'close', 'volume']

model = Sequential()
# print(FEATURE_COLUMNS)

split = int(len(df)*0.8)
train_df = df.iloc[:split]
test_df = df.iloc[split:]



scaler = StandardScaler()

train_scaled = scaler.fit_transform(train_df[FEATURE_COLUMNS])
test_scaled = scaler.transform(test_df[FEATURE_COLUMNS])

WINDOW_SIZE = 60

def create_sequences(data, window_size):
    X = []

    for i in range(len(data) - window_size):
        X.append(data[i:i+window_size])

    return np.array(X)
X_train = create_sequences(train_scaled, WINDOW_SIZE)
X_test = create_sequences(test_scaled, WINDOW_SIZE)

n_features = X_train.shape[2]

model = Sequential([

    LSTM(64, activation='tanh', input_shape=(WINDOW_SIZE, n_features), return_sequences=False),

    Dense(32),

    RepeatVector(WINDOW_SIZE),

    LSTM(64, activation='tanh', return_sequences=True),

    TimeDistributed(Dense(n_features))
])

model.compile(
    optimizer='adam',
    loss='mse'
)

model.summary()

history = model.fit(
    X_train,
    X_train,
    epochs=35,
    batch_size=128,
    validation_split=0.1,
    shuffle=False
)

train_pred = model.predict(X_train)

train_loss = tf.keras.losses.mse(
    X_train,
    train_pred
)

train_loss = np.mean(train_loss, axis=1)

test_pred = model.predict(X_test)

test_loss = tf.keras.losses.mse(
    X_test,
    test_pred
)

test_loss = np.mean(test_loss, axis=1)

threshold = np.percentile(train_loss, 99)
print(threshold)

anomalies = test_loss > threshold

print(anomalies.sum())

model.save("/Users/inainz/workspace/RichClub/model/seongsu/lstm_anomaly_model.keras")
joblib.dump(scaler, "/Users/inainz/workspace/RichClub//model/seongsu/scaler.pkl")
joblib.dump(threshold, "/Users/inainz/workspace/RichClub//model/seongsu/threshold.pkl")