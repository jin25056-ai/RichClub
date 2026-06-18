from xgboost import XGBRegressor
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_DB = os.getenv(MONGO_URI)
client = MongoClient(MONGO_DB)
db = client['data_seongsu']
collection = db['stock_data']
list(collection.find({}, {"_id": 1}).sort("date", -1).limit(10))

# docs = db.collection.find(
#     {"status": "done"},
#     {"_id": 1}
# ).sort("createdAt", 1).limit(300)

# ids = [doc["_id"] for doc in docs]

# db.collection.delete_many({"_id": {"$in": ids}})
# data = collection.find({})
# print(data)