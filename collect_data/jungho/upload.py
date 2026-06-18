import os
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
DATA_PATH = os.getenv("DATA_PATH")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# csv 파일만 필터
files = [f for f in os.listdir(DATA_PATH) if f.endswith(".csv")]

all_data = []

for file in files:
    file_path = os.path.join(DATA_PATH, file)

    # CSV 읽기
    df = pd.read_csv(file_path)

    stock_name = file.replace(".csv", "")
    df["stock_name"] = stock_name

    records = df.to_dict(orient="records")
    all_data.extend(records)

if all_data:
    collection.insert_many(all_data)

print(f"업로드 완료: {len(all_data)} rows")