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

# 💡 최신 XGBoost v4 모델 로드
MODEL_PATH = "../../model/jungho/stock_model_v4.pkl"

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

# ===== 5. Feature 생성 (XGBoost 학습 코드와 100% 동일) =====
df["ma5_ratio"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(5).mean()) / df["close"]
df["ma10_ratio"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(10).mean()) / df["close"]
df["ma20_ratio"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(20).mean()) / df["close"]

df["return"] = df.groupby("stock_name")["close"].pct_change()

df["macd_diff"] = df["macd"] - df["signal"]
df["macd_diff_ratio"] = df["macd_diff"] / df["close"]

# ===== 6. Target (실제값) 생성 =====
df["next_close"] = df.groupby("stock_name")["close"].shift(-1)
df["next_return"] = (df["next_close"] / df["close"]) - 1

# 💡 XGBoost 학습용 정답지와 동일하게 3클래스 설정 (0, 1, 2)
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

# 학습 코드와 동일하게 상위 80% 시점 이후의 미래 데이터(Test Set)만 필터링
unique_dates = sorted(df[date_col].unique())
split_date_idx = int(len(unique_dates) * 0.8)
split_date = unique_dates[split_date_idx]

print(f"📅 검증용 날짜 기준: {split_date} 이후의 미래 데이터만 평가합니다. (XGBoost)")

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

# ===== 8. 예측 (안전 마진 확률 필터링 적용) =====
# 각 클래스별 확률을 받습니다. (예: [[0.3, 0.35, 0.35], ...])
pred_probs = model.predict_proba(X_test)

# 일단 전부 HOLD(1)로 채워둔 기본 판을 만듭니다.
custom_preds = np.ones(len(X_test), dtype=int)

for i, probs in enumerate(pred_probs):
    # BUY(2) 확률이 확실하게 0.40(40%)을 넘을 때만 BUY 신호 허용
    if probs[2] >= 0.40:
        custom_preds[i] = 2
    # SELL(0) 확률이 확실하게 0.40(40%)을 넘을 때만 SELL 신호 허용
    elif probs[0] >= 0.40:
        custom_preds[i] = 0
    # 둘 다 40%를 못 넘고 비등비등하면?
    # 초기값인 1(HOLD)을 유지해서 억지 매매를 차단합니다.
    else:
        custom_preds[i] = 1

test_df["prediction"] = custom_preds

# ===== 9. 결과 해석 =====
test_df["trade_signal"] = test_df["prediction"].map({
    2: "BUY (상승 예상)",
    1: "HOLD (관망/횡보)",
    0: "SELL (하락 예상)"
})

# ===== 10. 성능 평가 =====
accuracy = accuracy_score(y_true, test_df["prediction"])
cm = confusion_matrix(y_true, test_df["prediction"])
report = classification_report(y_true, test_df["prediction"], target_names=["SELL (0)", "HOLD (1)", "BUY (2)"])

# ===== 11. 출력 =====
print("\n==============================")
print("📊 XGBoost 모델 성능 평가 결과 (Pure Test Set)")
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

# 💡 오타 수정 완료: 대괄호 [[ ]] 안에 깔끔하게 정돈했습니다.
print(test_df[["stock_name", date_col, "close", "actual", "prediction", "trade_signal"]].tail(20))

# ===== 13. 피처별 중요도 추출 =====
importances = model.feature_importances_
indices = np.argsort(importances)[::-1]

print("\n📊 XGBoost 피처 중요도 순위:")
for f in range(X_test.shape[1]):
    print(f"{f + 1}. {features[indices[f]]} ({importances[indices[f]]:.4f})")


# ===== 14. 시각화 =====
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

plt.figure(figsize=(7,6))

sns.heatmap(
    cm,
    annot=True,
    fmt="d",
    cmap="Blues",
    xticklabels=["SELL (0)", "HOLD (1)", "BUY (2)"],
    yticklabels=["SELL (0)", "HOLD (1)", "BUY (2)"]
)

plt.title("XGBoost Confusion Matrix (Test Set)")
plt.xlabel("Predicted")
plt.ylabel("Actual")
plt.show()