import os
import pandas as pd
from pymongo import MongoClient
from sklearn.ensemble import RandomForestClassifier
import joblib
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

# ===== 1. 데이터 가져오기 =====
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

df = pd.DataFrame(list(collection.find()))

# ===== 2. 정렬 =====
df = df.sort_values(["stock_name", "Date"])

# ===== 3. feature 생성 =====
df["ma5"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(5).mean())
df["ma10"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(10).mean())
df["ma20"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(20).mean())

df["return"] = df.groupby("stock_name")["close"].pct_change()

# RSI / MACD는 이미 DB에 있다고 가정
df["macd_diff"] = df["macd"] - df["signal"]

# ===== 4. target 생성 =====
df["next_close"] = df.groupby("stock_name")["close"].shift(-1)
df["target"] = (df["next_close"] > df["close"]).astype(int)

# ===== 5. 데이터 정리 =====
df = df.dropna()

# ===== 6. feature / label =====
features = [
    "ma5",
    "ma10",
    "ma20",
    "return",
    "rsi",
    "macd",
    "signal",
    "macd_diff"
]

X = df[features]
y = df["target"]

# ===== 7. 시간 기준 train/test split =====
split_idx = int(len(df) * 0.8)

X_train = X.iloc[:split_idx]
X_test = X.iloc[split_idx:]
y_train = y.iloc[:split_idx]
y_test = y.iloc[split_idx:]

# ===== 8. 모델 학습 =====
model = RandomForestClassifier(
    n_estimators=300,
    max_depth=12,
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

# ===== 9. 평가 =====
accuracy = model.score(X_test, y_test)
print("accuracy:", accuracy)

# ===== 10. 저장 =====
save_dir = "../../model/jungho"
os.makedirs(save_dir, exist_ok=True)

model_path = os.path.join(save_dir, "stock_model_v2.pkl")
joblib.dump(model, model_path)

print("model saved:", model_path)