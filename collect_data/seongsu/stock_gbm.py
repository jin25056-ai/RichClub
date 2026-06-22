from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix
)

import os
from xgboost import XGBClassifier
from pymongo import MongoClient
import pandas as pd

MONGO_URI  = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['data_hyerim']
collection = db['investor_trend']
# print('link db')
df = pd.DataFrame(list(collection.find({}, {"_id": 0})))

df = df.sort_values(['stock_code','date'])
summary = df.groupby('stock_code').agg({
    'individual' : ['sum','mean','std'],
    'foreign' : ['sum','mean','std'],
    'institution' : ['sum','mean','std']
})

summary.columns = [
    "individual_SUM", "individual_MEAN", "individual_STD",
    "foreign_SUM", "foreign_MEAN", "foreign_STD",
    "institution_SUM", "institution_MEAN", "institution_STD"
]

summary["외인기관_TOTAL"] = (
    summary["foreign_SUM"] + summary["institution_SUM"]
)

summary["수급_불균형"] = (
    summary["외인기관_TOTAL"] - summary["individual_SUM"]
)

summary["기관집중도"] = (
    summary["institution_STD"] / (summary["institution_MEAN"].abs() + 1)
)

summary["외인집중도"] = (
    summary["foreign_STD"] / (summary["foreign_MEAN"].abs() + 1)
)

summary["LABEL"] = 0

summary.loc[
    (summary["외인기관_TOTAL"] > 0) &
    (summary["수급_불균형"] > 0),
    "LABEL"
] = 1

feature_cols = [
    "foreign_SUM",
    "institution_SUM",
    "individual_SUM",
    "외인기관_TOTAL",
    "수급_불균형",
    "기관집중도",
    "외인집중도"
]

X = summary[feature_cols]
y = summary["LABEL"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

model = XGBClassifier(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42
            )
model.fit(X, y)

pred = model.predict(X_test)

acc = accuracy_score(y_test, pred)
precision = precision_score(y_test, pred)
recall = recall_score(y_test, pred)
f1 = f1_score(y_test, pred)

print("Accuracy:", acc)
print("Precision:", precision)
print("Recall:", recall)
print("F1 Score:", f1)

cm = confusion_matrix(y_test, pred)
print(cm)

# 전체 종목에 대해 예측
summary["SELYEOK"] = model.predict(summary[feature_cols])

# 확률(신뢰도)
summary["CONFIDENCE"] = model.predict_proba(
    summary[feature_cols]
)[:, 1]

result = summary[[
    "SELYEOK",
    "CONFIDENCE"
]]

print(result)