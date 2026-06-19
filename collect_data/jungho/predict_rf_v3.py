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

# 최신 v3 다중 분류 모델 로드
MODEL_PATH = "../../model/jungho/stock_model_v3.pkl"

# ===== 2. 모델 로드 =====
model = joblib.load(MODEL_PATH)

# ===== 3. MongoDB 데이터 로드 =====
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

df = pd.DataFrame(list(collection.find()))

# ===== 4. 데이터 정렬 및 기본 정리 =====
if "_id" in df.columns:
    df = df.drop(columns=["_id"])

date_col = "Date" if "Date" in df.columns else "date"
df = df.sort_values(["stock_name", date_col])

# ===== 5. Feature 생성 (학습 코드와 100% 동일) =====
df["ma5_ratio"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(5).mean()) / df["close"]
df["ma10_ratio"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(10).mean()) / df["close"]
df["ma20_ratio"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(20).mean()) / df["close"]

df["return"] = df.groupby("stock_name")["close"].pct_change()

df["macd_diff"] = df["macd"] - df["signal"]
df["macd_diff_ratio"] = df["macd_diff"] / df["close"]

# ===== 6. Target (실제값) 생성 =====
df["next_close"] = df.groupby("stock_name")["close"].shift(-1)
df["next_return"] = (df["next_close"] / df["close"]) - 1

# 수정 포인트: 학습 모델과 똑같이 3클래스 실제 정답지 생성
df["actual"] = np.select(
    [
        df["next_return"] >= 0.01,
        df["next_return"] <= -0.01
    ],
    [2, 0],
    default=1
)

# ===== 7. 데이터 정리 (결측치 제거) =====
df = df.dropna()

# train_model_v3와 똑같은 날짜 기준으로 미래 데이터만 필터링!
unique_dates = sorted(df[date_col].unique())
split_date_idx = int(len(unique_dates) * 0.8)
split_date = unique_dates[split_date_idx]

print(f"📅 검증용 날짜 기준: {split_date} 이후의 미래 데이터만 평가합니다.")

# 오직 학습에 사용되지 않은 미래 데이터(Test Set)만 남깁니다.
test_df = df[df[date_col] >= split_date].copy()

features = [
    "ma5_ratio",
    "ma10_ratio",
    "ma20_ratio",
    "return",
    "rsi",
    "macd_diff_ratio"
]
X_test = test_df[features]
y_true = test_df["actual"]

# ===== 8. 예측 (다중 확률 기반 예측) =====
# 모델이 각 클래스별(0, 1, 2)로 계산한 확률을 가져옵니다.
pred_probs = model.predict_proba(X_test)

# 그중 가장 높은 확률을 가진 클래스의 인덱스를 최종 예측값으로 채택합니다.
test_df["prediction"] = np.argmax(pred_probs, axis=1)

# ===== 9. 결과 해석 =====
# 3가지 신호 이름 맵핑
test_df["trade_signal"] = test_df["prediction"].map({
    2: "BUY (상승 예상)",
    1: "HOLD (관망/횡보)",
    0: "SELL (하락 예상)"
})

# ===== 10. 성능 평가 =====
accuracy = accuracy_score(y_true, test_df["prediction"])
cm = confusion_matrix(y_true, test_df["prediction"])
# 레포트에 3개 레이블 이름 적용
report = classification_report(y_true, test_df["prediction"], target_names=["SELL (0)", "HOLD (1)", "BUY (2)"])

# ===== 11. 출력 =====
print("\n==============================")
print("📊 모델 성능 평가 결과 (Pure Test Set - v3)")
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

print(test_df[["stock_name", date_col, "close", "actual", "prediction", "trade_signal"]].tail(20))

# ===== 13. 피처별 중요도 추출 =====
importances = model.feature_importances_
indices = np.argsort(importances)[::-1]

print("\n📊 피처 중요도 순위:")
for f in range(X_test.shape[1]):
    print(f"{f + 1}. {features[indices[f]]} ({importances[indices[f]]:.4f})")


# ===== 14. 시각화 =====
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

plt.figure(figsize=(7,6))

# 💡 히트맵 축 레이블을 3개(SELL, HOLD, BUY)로 확장
sns.heatmap(
    cm,
    annot=True,
    fmt="d",
    cmap="Blues",
    xticklabels=["SELL (0)", "HOLD (1)", "BUY (2)"],
    yticklabels=["SELL (0)", "HOLD (1)", "BUY (2)"]
)

plt.title("Confusion Matrix (Test Set - v3)")
plt.xlabel("Predicted")
plt.ylabel("Actual")
plt.show()