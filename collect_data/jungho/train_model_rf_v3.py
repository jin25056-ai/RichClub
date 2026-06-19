import os
import pandas as pd
import numpy as np
from pymongo import MongoClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_sample_weight # 💡 다중 분류 가중치용 추가
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

# ===== 3. feature 생성 및 비율(Ratio) 변환 =====
df["ma5_ratio"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(5).mean()) / df["close"]
df["ma10_ratio"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(10).mean()) / df["close"]
df["ma20_ratio"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(20).mean()) / df["close"]

df["return"] = df.groupby("stock_name")["close"].pct_change()

df["macd_diff"] = df["macd"] - df["signal"]
df["macd_diff_ratio"] = df["macd_diff"] / df["close"]

# ===== 4. 다중 분류 target 생성 (매수/매도/관망) =====
df["next_close"] = df.groupby("stock_name")["close"].shift(-1)
df["next_return"] = (df["next_close"] / df["close"]) - 1

# 💡 조건 설정: +1% 이상 매수(2), -1% 이하 매도(0), 그 사이 박스권 횡보는 관망(1)
df["target"] = np.select(
    [
        df["next_return"] >= 0.01,
        df["next_return"] <= -0.01
    ],
    [2, 0],
    default=1
)

# ===== 5. 데이터 정리 =====
df = df.dropna()

# ===== 6. feature / label 선택 =====
features = [
    "ma5_ratio",
    "ma10_ratio",
    "ma20_ratio",
    "return",
    "rsi",
    "macd_diff_ratio"
]

X = df[features]
y = df["target"]

# ===== 7. 시간 기준 train/test split =====
unique_dates = sorted(df["Date"].unique())
split_date_idx = int(len(unique_dates) * 0.8)
split_date = unique_dates[split_date_idx]

print(f"📅 기준 분할 날짜: {split_date} (이전은 Train, 이후는 Test)")

train_mask = df["Date"] < split_date
test_mask = df["Date"] >= split_date

X_train = X[train_mask]
X_test = X[test_mask]
y_train = y[train_mask]
y_test = y[test_mask]

print(f"Train 데이터 수: {len(X_train)}, Test 데이터 수: {len(X_test)}")

# ===== 8. 모델 학습 =====
# 💡 클래스가 3개인 다중 분류에서는 class_weight="balanced"가 간혹 불안정할 수 있으므로,
# 확실하게 샘플별 가중치를 계산해 주입하는 방식을 사용합니다.
sample_weight = compute_sample_weight(class_weight="balanced", y=y_train)

model = RandomForestClassifier(
    n_estimators=300,
    max_depth=12,
    random_state=42,
    n_jobs=-1
)

# 학습 시 가중치 배열 주입
model.fit(X_train, y_train, sample_weight=sample_weight)

# ===== 9. 평가 및 피처 중요도 출력 =====
# 💡 다중 분류는 이제 3가지(0, 1, 2) 확률을 배열로 뱉습니다.
pred_probs = model.predict_proba(X_test)

# 💡 그중 가장 확률이 높은 클래스의 인덱스(0, 1, 2)를 최종 예측값으로 채택합니다.
custom_preds = np.argmax(pred_probs, axis=1)

# 지표 출력 (target_names 추가로 레포트를 직관적으로 보기 쉽게 변경)
accuracy = accuracy_score(y_test, custom_preds)
cm = confusion_matrix(y_test, custom_preds)
report = classification_report(y_test, custom_preds, target_names=["SELL (0)", "HOLD (1)", "BUY (2)"])

print("\n==============================")
print("📊 클래스(매수/매도/관망) v3 성능 평가")
print("==============================\n")
print(f"Accuracy: {accuracy:.4f}\n")
print("Confusion Matrix:")
print(cm)
print("\nClassification Report:")
print(report)
print("==============================\n")

# 피처 중요도 출력
importances = model.feature_importances_
indices = np.argsort(importances)[::-1]

print("v3 피처 중요도 순위:")
for f in range(X_train.shape[1]):
    print(f"{f + 1}. {features[indices[f]]} ({importances[indices[f]]:.4f})")

# ===== 10. 저장 =====
save_dir = "../../model/jungho"
os.makedirs(save_dir, exist_ok=True)

model_path = os.path.join(save_dir, "stock_model_v3.pkl")
joblib.dump(model, model_path)

print("\nmodel saved:", model_path)