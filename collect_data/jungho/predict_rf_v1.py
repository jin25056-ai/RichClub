import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pymongo import MongoClient
import joblib

from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
from dotenv import load_dotenv

load_dotenv()

# ===== 1. 환경 설정 =====
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

MODEL_PATH = "../../model/jungho/stock_model_v1.pkl"

# ===== 2. 모델 로드 =====
model = joblib.load(MODEL_PATH)

# ===== 3. MongoDB 데이터 로드 =====
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

df = pd.DataFrame(list(collection.find()))

# ===== 4. 데이터 정리 =====
if "_id" in df.columns:
    df = df.drop(columns=["_id"])

date_col = "Date" if "Date" in df.columns else "date"

df = df.sort_values(["stock_name", date_col])

# ===== 5. Feature 생성 (train과 반드시 동일) =====
df["ma5"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(5).mean())
df["ma10"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(10).mean())
df["return"] = df.groupby("stock_name")["close"].pct_change()

# ===== 6. Target (실제값) 생성 =====
df["next_close"] = df.groupby("stock_name")["close"].shift(-1)
df["actual"] = (df["next_close"] > df["close"]).astype(int)

# ===== 7. 데이터 정리 =====
df = df.dropna()

features = ["ma5", "ma10", "return"]
X = df[features]
y_true = df["actual"]

# ===== 8. 예측 =====
df["prediction"] = model.predict(X)

# ===== 9. 결과 해석 =====
df["signal"] = df["prediction"].map({
    1: "BUY (상승 예상)",
    0: "SELL (하락 예상)"
})

# ===== 10. 성능 평가 =====
accuracy = accuracy_score(y_true, df["prediction"])
cm = confusion_matrix(y_true, df["prediction"])
report = classification_report(y_true, df["prediction"])

# ===== 11. 출력 =====
print("\n==============================")
print("📊 모델 성능 평가 결과")
print("==============================\n")

print(f"Accuracy: {accuracy:.4f}\n")

print("Confusion Matrix:")
print(cm)

print("\nClassification Report:")
print(report)

# ===== 12. 최근 예측 결과 =====
print("\n==============================")
print("📈 최근 예측 결과")
print("==============================\n")

print(df[["stock_name", date_col, "close", "actual", "prediction", "signal"]].tail(20))

# ===== 13. 피처별 중요도 추출 =====
importances = model.feature_importances_
indices = np.argsort(importances)[::-1]

print("📊 피처 중요도 순위:")
for f in range(X.shape[1]):
    print(f"{f + 1}. {features[indices[f]]} ({importances[indices[f]]:.4f})")

# ===== 14. 시각화 =====
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

plt.figure(figsize=(6,5))

sns.heatmap(
    cm,
    annot=True,
    fmt="d",
    cmap="Blues",
    xticklabels=["SELL (0)", "BUY (1)"],
    yticklabels=["SELL (0)", "BUY (1)"]
)

plt.title("Confusion Matrix")
plt.xlabel("Predicted")
plt.ylabel("Actual")
plt.show()