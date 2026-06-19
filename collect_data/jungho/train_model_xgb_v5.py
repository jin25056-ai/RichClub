import os
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib

# ⭐ 가상환경 리셋 후 가장 안전하게 돌아가는 XGBoost 임포트
from xgboost import XGBClassifier

# ===== 1. 환경 변수 및 몽고DB 데이터 가져오기 =====
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

raw_df = pd.DataFrame(list(collection.find()))

# ===== 2. 데이터 기본 정제 (소문자 변환 및 Date 정렬) =====
if '_id' in raw_df.columns:
    raw_df.drop(columns=['_id'], inplace=True)

raw_df.columns = [col.lower() for col in raw_df.columns]

if 'date' in raw_df.columns:
    raw_df['date'] = pd.to_datetime(raw_df['date'])
    raw_df.sort_values('date', ascending=True, inplace=True)
    raw_df.reset_index(drop=True, inplace=True)


# ===== 3. 기존 컬럼 활용 및 조건 필터링 함수 =====
def build_dataset_with_existing_data(df):
    df = df.copy()

    # 1) 이평선 및 기본 지표 계산
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma60'] = df['close'].rolling(window=60).mean()
    df['is_5d_high'] = df['high'] == df['high'].rolling(5).max()

    # 2) 내 데이터 안의 기존 'macd'를 활용해 'macd_signal' 직접 계산하기 ⚡
    # MACD 시그널 선의 표준 공식은 MACD 선의 9일 지수이동평균(EMA)입니다.
    db_macd = df['macd']
    db_macd_signal = db_macd.ewm(span=9, adjust=False).mean() # 내장 함수로 시그널 즉석 생성!

    # 3) 스토캐스틱 Slow 계산 (K=12, D=5)
    low_min = df['low'].rolling(window=12).min()
    high_max = df['high'].rolling(window=12).max()
    fast_k = 100 * ((df['close'] - low_min) / (high_max - low_min))
    df['stoch_k'] = fast_k.rolling(window=3).mean()
    df['stoch_d'] = df['stoch_k'].rolling(window=5).mean()

    # 4) AI 모델용 파생 Feature 생성
    df['ma5_20_ratio'] = df['ma5'] / df['ma20']
    df['ma20_60_ratio'] = df['ma20'] / df['ma60']
    df['close_ma60_ratio'] = df['close'] / df['ma60']
    df['vol_change'] = df['volume'].pct_change()

    # ===== 매수 조건 필터링 =====
    cond_ma60 = df['close'] >= df['ma60']
    cond_macd = db_macd > db_macd_signal                             # 직접 만든 시그널과 비교 가동!
    cond_stoch = df['stoch_k'] > df['stoch_d']
    cond_ma_trend = (df['ma5'] > df['ma20']) & df['is_5d_high']

    buy_candidates = df[cond_ma60 & cond_macd & cond_stoch & cond_ma_trend].copy()

    # ===== Label(정답) 생성 =====
    buy_candidates['future_max_high'] = buy_candidates['high'].shift(-5).rolling(5).max()
    buy_candidates['target'] = (buy_candidates['future_max_high'] >= buy_candidates['close'] * 1.03).astype(int)

    # ⚡ [여기에 추가] 무한대(inf, -inf) 값을 결측치(NaN)로 치환합니다.
    buy_candidates.replace([np.inf, -np.inf], np.nan, inplace=True)

    # target 및 학습에 쓸 주요 feature들의 결측치를 싹 지웁니다.
    buy_candidates.dropna(subset=['target', 'ma5_20_ratio', 'vol_change', 'stoch_k'], inplace=True)

    return buy_candidates


# 데이터 가공
dataset = build_dataset_with_existing_data(raw_df)

feature_cols = ['ma5_20_ratio', 'ma20_60_ratio', 'close_ma60_ratio', 'vol_change', 'macd', 'rsi', 'stoch_k', 'stoch_d']
X = dataset[feature_cols]
y = dataset['target']

if len(X) < 10:
    print(f"❌ 매수 조건 만족 데이터 부족 (현재: {len(X)}개).")
else:
    # ===== 4. 데이터 분할 =====
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    # ===== 5. XGBClassifier 모델 생성 및 학습 =====
    model = XGBClassifier(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=4,
        random_state=42,
        eval_metric='logloss'
    )

    # 학습 시작
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False
    )

    # ===== 6. 테스트 데이터 평가 및 예측 =====
    y_pred = model.predict(X_test)

    print("-" * 50)
    print(f"🎯 최종 모델 정확도(Accuracy): {accuracy_score(y_test, y_pred):.4f}")
    print("-" * 50)
    print("[상세 분류 레포트]")
    print(classification_report(y_test, y_pred, target_names=['실패(0)', '성공(1)']))

    # ===== 7. 모델 pkl 저장 =====
    # model_filename = "xgb_trading_model.pkl"
    # joblib.dump(model, model_filename)
    # print(f"💾 XGBoost 모델 저장 완료: {model_filename}")

    import matplotlib.pyplot as plt
    import seaborn as sns
    from sklearn.metrics import confusion_matrix

    # 한글 깨짐 방지 설정 (Windows 기준 맑은 고딕 적용)
    plt.rc('font', family='Malgun Gothic')
    plt.rc('axes', unicode_minus=False)

    # ===== 8. 혼동 행렬(Confusion Matrix) 계산 =====
    # y_test: 실제 정답, y_pred: 모델이 예측한 값
    cm = confusion_matrix(y_test, y_pred)

    # ===== 9. Heatmap 그리기 =====
    plt.figure(figsize=(8, 6))

    # sns.heatmap을 이용해 혼동 행렬을 시각화합니다.
    sns.heatmap(
        cm,
        annot=True,  # 각 칸에 실제 수치 표시
        fmt='d',  # 정수 형태(digit)로 표시
        cmap='Blues',  # 푸른색 계열 색상 테마
        xticklabels=['실패 예측(0)', '성공 예측(1)'],
        yticklabels=['실제 실패(0)', '실제 성공(1)']
    )

    plt.title('트레이딩 모델 혼동 행렬 (Confusion Matrix) Heatmap', fontsize=14, pad=15)
    plt.xlabel('모델의 예측 (Predicted)', fontsize=12, labelpad=10)
    plt.ylabel('실제 결과 (Actual)', fontsize=12, labelpad=10)

    # 그래프 출력
    plt.tight_layout()
    plt.show()