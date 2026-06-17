import os
import pandas as pd
from pymongo import MongoClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib
from dotenv import load_dotenv  # .env 파일 읽어오는 라이브러리

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
# 최근 5일 평균 가격
df["ma5"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(5).mean())
# 최근 10일 평균 가격
df["ma10"] = df.groupby("stock_name")["close"].transform(lambda x: x.rolling(10).mean())
# 하루 수익률
df["return"] = df.groupby("stock_name")["close"].pct_change()

# ===== 4. target 생성 =====
# 다음날 가격 가져오기
df["next_close"] = df.groupby("stock_name")["close"].shift(-1)
# 내일 가격이 오늘보다 높으면 1 아니면 0 (1 : 상승, 0 : 하락)
df["target"] = (df["next_close"] > df["close"]).astype(int)

# ===== 5. 데이터 정리 =====
df = df.dropna()

features = ["ma5", "ma10", "return"]
X = df[features]
y = df["target"]

# ===== 6. train/test =====
X_train, X_test, y_train, y_test = train_test_split(X, y, shuffle=False)

# ===== 7. 모델 학습 =====
model = RandomForestClassifier(n_estimators=200)
model.fit(X_train, y_train)

# ===== 8. 평가 =====
print("accuracy:", model.score(X_test, y_test))

# ===== 9. 저장 =====
# 저장할 디렉토리 경로 설정
save_dir = "../../model/jungho"

# 해당 디렉토리가 없으면 자동으로 생성
# os.makedirs(save_dir, exist_ok=True)

# 모델 저장 경로 결합
model_path = os.path.join(save_dir, "stock_model_v1.pkl")
# 모델 저장
joblib.dump(model, model_path)