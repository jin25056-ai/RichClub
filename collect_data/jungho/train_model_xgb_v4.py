import os
import platform
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pymongo import MongoClient
from xgboost import XGBClassifier
from sklearn.metrics import (
    classification_report, confusion_matrix,
    precision_score, recall_score
)
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.model_selection import TimeSeriesSplit
import joblib
from dotenv import load_dotenv

load_dotenv()

# ===================================================================
# 0. 한글 폰트 설정
# ===================================================================
system = platform.system()
if system == "Windows":
    plt.rcParams["font.family"] = "Malgun Gothic"
elif system == "Darwin":
    plt.rcParams["font.family"] = "AppleGothic"
else:
    try:
        import koreanize_matplotlib  # noqa
    except ImportError:
        plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False

# ===================================================================
# 1. 데이터 로드
# ===================================================================
client     = MongoClient(os.getenv("MONGO_URI"))
db         = client[os.getenv("DB_NAME")]
collection = db[os.getenv("COLLECTION_NAME")]

df = pd.DataFrame(list(collection.find()))
df = df.sort_values(["stock_name", "Date"]).reset_index(drop=True)

# ===================================================================
# 2. 시간 분할 (Leakage 방지)
# ===================================================================
unique_dates = sorted(df["Date"].unique())
split_date   = unique_dates[int(len(unique_dates) * 0.8)]

train_mask = df["Date"] < split_date
test_mask  = df["Date"] >= split_date

# ===================================================================
# 3. Feature 계산 (11개)
# ===================================================================
g = df.groupby("stock_name")

# 추세 (3개)
df["ma5"]      = g["close"].transform(lambda x: x.rolling(5).mean())
df["ma20"]     = g["close"].transform(lambda x: x.rolling(20).mean())
df["ma5_ratio"]  = df["ma5"]  / df["close"]
df["ma20_ratio"] = df["ma20"] / df["close"]
df["high_20"]    = g["close"].transform(lambda x: x.rolling(20).max())
df["drawdown"]   = df["close"] / df["high_20"] - 1   # 고점 대비 낙폭

# 모멘텀 (2개)
df["return"]     = g["close"].transform(lambda x: x.pct_change())
df["momentum_5"] = g["close"].transform(lambda x: x.pct_change(5))

# 오실레이터 (2개)
df["macd_diff"]       = df["macd"] - df["signal"]
df["macd_diff_ratio"] = df["macd_diff"] / df["close"]
# rsi는 DB에서 그대로 사용

# 변동성 (1개) — z-score 정규화
df["volatility_raw"] = g["return"].transform(lambda x: x.rolling(10).std())
df["volatility_z"]   = g["volatility_raw"].transform(
    lambda x: (x - x.rolling(60).mean()) / (x.rolling(60).std() + 1e-9)
)

# 거래량 (1개)
df["volume_spike"] = df["volume"] / g["volume"].transform(lambda x: x.rolling(20).mean())

# 시장 (2개) — Train / Test 독립 계산
train_market = (
    df[train_mask].groupby("Date")["close"].mean()
    .pct_change().rename("market_return")
)
test_market = (
    df[test_mask].groupby("Date")["close"].mean()
    .pct_change().rename("market_return")
)
df = df.join(pd.concat([train_market, test_market]), on="Date")
df["relative_strength"] = df["return"] - df["market_return"]

# ===================================================================
# 4. Target: 3-class (SELL=0, HOLD=1, BUY=2)
# ===================================================================
df["next_close"]  = g["close"].transform(lambda x: x.shift(-3))
df["next_return"] = (df["next_close"] / df["close"]) - 1

def make_label(r):
    if r >= 0.02:    return 2   # BUY
    elif r <= -0.02: return 0   # SELL
    else:            return 1   # HOLD

df["target"] = df["next_return"].apply(make_label)

# ===================================================================
# 5. 결측치 제거 후 mask 재계산
# ===================================================================
df = df.dropna().reset_index(drop=True)
train_mask = df["Date"] < split_date
test_mask  = df["Date"] >= split_date

# ===================================================================
# 6. Feature 목록 (11개)
# ===================================================================
features = [
    "ma5_ratio",         # 단기 추세
    "ma20_ratio",        # 중기 추세
    "drawdown",          # 고점 대비 낙폭
    "return",            # 단기 수익률
    "momentum_5",        # 중기 모멘텀
    "rsi",               # RSI
    "macd_diff_ratio",   # MACD 방향성
    "volatility_z",      # 변동성 z-score
    "volume_spike",      # 거래량 급등
    "market_return",     # 시장 방향
    "relative_strength", # 개별 종목 상대강도
]

X_train = df.loc[train_mask, features]
y_train = df.loc[train_mask, "target"]
X_test  = df.loc[test_mask,  features]
y_test  = df.loc[test_mask,  "target"]

print(f"Train 기간 : {df.loc[train_mask, 'Date'].min()} ~ {df.loc[train_mask, 'Date'].max()}")
print(f"Test  기간 : {df.loc[test_mask,  'Date'].min()} ~ {df.loc[test_mask,  'Date'].max()}")
print(f"Train 샘플 : {len(X_train):,}  |  Test 샘플 : {len(X_test):,}\n")

print("Train 클래스 분포:")
vc = y_train.value_counts().sort_index()
vc.index = ["SELL", "HOLD", "BUY"]
print(vc, "\n")

print("Test 클래스 분포:")
vc2 = y_test.value_counts().sort_index()
vc2.index = ["SELL", "HOLD", "BUY"]
print(vc2, "\n")

# ===================================================================
# 7. Sample Weight (balanced + volume_spike 높은 샘플 2배)
# ===================================================================
extra_weight  = np.where(df.loc[train_mask, "volume_spike"] > 1.2, 2.0, 1.0)
sample_weight = compute_sample_weight("balanced", y_train) * extra_weight

# ===================================================================
# 8. TimeSeriesSplit 교차검증
# ===================================================================
print("=" * 55)
print("TimeSeriesSplit 교차검증 (5-fold)")
print("=" * 55)

tscv = TimeSeriesSplit(n_splits=5)
cv_results = {"SELL": [], "HOLD": [], "BUY": []}

for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_train)):
    X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
    y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]

    ew = np.where(df.loc[train_mask].iloc[tr_idx]["volume_spike"] > 1.2, 2.0, 1.0)
    w  = compute_sample_weight("balanced", y_tr) * ew

    cv_model = XGBClassifier(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.02,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        gamma=0.1,
        random_state=42,
        n_jobs=-1,
        num_class=3,
        objective="multi:softprob",
        eval_metric="mlogloss"
    )
    cv_model.fit(X_tr, y_tr, sample_weight=w)

    val_preds = cv_model.predict(X_val)
    report    = classification_report(y_val, val_preds, output_dict=True, zero_division=0)

    cv_results["SELL"].append(report.get("0", {}).get("f1-score", 0))
    cv_results["HOLD"].append(report.get("1", {}).get("f1-score", 0))
    cv_results["BUY" ].append(report.get("2", {}).get("f1-score", 0))

    print(f"  Fold {fold+1} | SELL f1={cv_results['SELL'][-1]:.4f}  "
          f"HOLD f1={cv_results['HOLD'][-1]:.4f}  BUY f1={cv_results['BUY'][-1]:.4f}")

print()
for cls in ["SELL", "HOLD", "BUY"]:
    arr = cv_results[cls]
    print(f"  {cls} 평균 f1: {np.mean(arr):.4f} ± {np.std(arr):.4f}")
print()

# ===================================================================
# 9. 최종 모델 학습
# ===================================================================
print("=" * 55)
print("최종 모델 학습 (3-class: SELL / HOLD / BUY)")
print("=" * 55)

model = XGBClassifier(
    n_estimators=1000,
    max_depth=5,
    learning_rate=0.02,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,
    gamma=0.1,
    random_state=42,
    n_jobs=-1,
    num_class=3,
    objective="multi:softprob",
    eval_metric="mlogloss",
    early_stopping_rounds=50
)

model.fit(
    X_train, y_train,
    sample_weight=sample_weight,
    eval_set=[(X_test, y_test)],
    verbose=50
)

print(f"\n최적 트리 수: {model.best_iteration}\n")

# ===================================================================
# 10. 예측
# ===================================================================
probs     = model.predict_proba(X_test)
preds     = model.predict(X_test)
prob_sell = probs[:, 0]
prob_hold = probs[:, 1]
prob_buy  = probs[:, 2]

print("BUY  확률 분포:"); print(pd.Series(prob_buy).describe())
print("\nSELL 확률 분포:"); print(pd.Series(prob_sell).describe()); print()

# ===================================================================
# 11. Threshold별 성능 테이블
# ===================================================================
print("=" * 75)
print("Threshold별 BUY / SELL 성능")
print("=" * 75)

thresholds = [0.35, 0.38, 0.40, 0.43, 0.45, 0.50]
rows = []

for t in thresholds:
    buy_sig  = (prob_buy  >= t)
    sell_sig = (prob_sell >= t)

    buy_returns  = df.loc[test_mask, "next_return"].values[buy_sig]
    sell_returns = df.loc[test_mask, "next_return"].values[sell_sig]

    rows.append({
        "Threshold"    : t,
        "BUY Prec"     : round(precision_score(y_test == 2, buy_sig,  zero_division=0), 4),
        "BUY Recall"   : round(recall_score(   y_test == 2, buy_sig,  zero_division=0), 4),
        "BUY N"        : int(buy_sig.sum()),
        "BUY MeanRet"  : f"{buy_returns.mean():.2%}"         if len(buy_returns)  else "N/A",
        "BUY WinRate"  : f"{(buy_returns>=0.02).mean():.1%}" if len(buy_returns)  else "N/A",
        "SELL Prec"    : round(precision_score(y_test == 0, sell_sig, zero_division=0), 4),
        "SELL Recall"  : round(recall_score(   y_test == 0, sell_sig, zero_division=0), 4),
        "SELL N"       : int(sell_sig.sum()),
        "SELL MeanRet" : f"{sell_returns.mean():.2%}"        if len(sell_returns) else "N/A",
    })

print(pd.DataFrame(rows).to_string(index=False))
print()

# ===================================================================
# 12. 최종 Classification Report
# ===================================================================
print("=" * 55)
print("최종 Classification Report (argmax 예측)")
print("=" * 55)
print(classification_report(
    y_test, preds,
    target_names=["SELL(0)", "HOLD(1)", "BUY(2)"],
    zero_division=0
))

# ===================================================================
# 13. Feature Importance
# ===================================================================
print("Feature Importance:")
fi = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
for name, val in fi.items():
    print(f"  {name:25s}: {val:.4f}")
print()

# ===================================================================
# 14. 시각화 (2행 2열)
# ===================================================================
BEST_T = 0.43

fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle("Stock Model v4 — SELL / HOLD / BUY (feature 11개)", fontsize=15, fontweight="bold")

# ── (1) Confusion Matrix Heatmap ─────────────────────────────────
cm      = confusion_matrix(y_test, preds)
labels  = ["SELL", "HOLD", "BUY"]
cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)

annot = np.empty_like(cm, dtype=object)
for i in range(3):
    for j in range(3):
        annot[i, j] = f"{cm[i,j]:,}\n({cm_norm[i,j]:.1%})"

sns.heatmap(
    cm_norm, annot=annot, fmt="",
    cmap="Blues",
    xticklabels=labels, yticklabels=labels,
    ax=axes[0, 0],
    linewidths=0.5, linecolor="gray",
    vmin=0, vmax=1
)
axes[0, 0].set_title("Confusion Matrix (행 기준 정규화)", fontsize=12)
axes[0, 0].set_xlabel("Predicted", fontsize=11)
axes[0, 0].set_ylabel("Actual",    fontsize=11)

# ── (2) 클래스별 예측 확률 분포 ──────────────────────────────────
colors = {"SELL": "steelblue", "HOLD": "gray", "BUY": "tomato"}
for cls_idx, cls_name in enumerate(["SELL", "HOLD", "BUY"]):
    axes[0, 1].hist(
        probs[y_test == cls_idx, cls_idx],
        bins=40, alpha=0.6,
        label=cls_name, color=colors[cls_name]
    )
axes[0, 1].axvline(BEST_T, color="black", linestyle="--", lw=1.5, label=f"threshold={BEST_T}")
axes[0, 1].set_title("클래스별 예측 확률 분포", fontsize=12)
axes[0, 1].set_xlabel("Predicted Probability")
axes[0, 1].set_ylabel("Count")
axes[0, 1].legend()

# ── (3) Threshold별 BUY / SELL Precision ─────────────────────────
t_range = np.arange(0.30, 0.65, 0.01)
buy_precs, sell_precs, buy_cnts, sell_cnts = [], [], [], []

for t in t_range:
    bp = (prob_buy  >= t)
    sp = (prob_sell >= t)
    buy_precs.append( precision_score(y_test == 2, bp, zero_division=0))
    sell_precs.append(precision_score(y_test == 0, sp, zero_division=0))
    buy_cnts.append(  int(bp.sum()))
    sell_cnts.append( int(sp.sum()))

ax3  = axes[1, 0]
ax3b = ax3.twinx()

ax3.plot(t_range, buy_precs,  color="tomato",    lw=2, label="BUY Precision")
ax3.plot(t_range, sell_precs, color="steelblue", lw=2, label="SELL Precision")
ax3b.bar(t_range, buy_cnts,  width=0.008, alpha=0.15, color="tomato",    label="BUY 신호수")
ax3b.bar(t_range, sell_cnts, width=0.008, alpha=0.15, color="steelblue", label="SELL 신호수",
         bottom=buy_cnts)
ax3.axvline(BEST_T, color="black", linestyle="--", lw=1.5, label=f"threshold={BEST_T}")

ax3.set_title("Threshold별 BUY / SELL Precision", fontsize=12)
ax3.set_xlabel("Threshold")
ax3.set_ylabel("Precision")
ax3b.set_ylabel("Signal Count")
ax3.legend(loc="upper left")
ax3b.legend(loc="upper right")
ax3.set_xlim([0.30, 0.65])
ax3.set_ylim([0, 1])

# ── (4) Feature Importance ────────────────────────────────────────
fi_sorted = fi.sort_values()
fi_sorted.plot(kind="barh", ax=axes[1, 1], color="steelblue", edgecolor="white")
axes[1, 1].set_title("Feature Importance (11개)", fontsize=12)
axes[1, 1].set_xlabel("Importance")

plt.tight_layout()

save_dir = "../../model/jungho"
os.makedirs(save_dir, exist_ok=True)
plt.savefig(os.path.join(save_dir, "evaluation_v4.png"), dpi=150, bbox_inches="tight")
plt.show()

# ===================================================================
# 15. 모델 저장
# ===================================================================
joblib.dump(model, os.path.join(save_dir, "stock_model_v4.pkl"))
print(f"✅ 모델 저장 완료: {os.path.join(save_dir, 'stock_model_v4.pkl')}")