import requests
import os
from dotenv import load_dotenv

load_dotenv()

SERVICE_KEY = os.getenv("SERVICE_KEY")

url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"

params = {
    "crtfc_key": SERVICE_KEY,
    "corp_code": "00126380",  # 삼성전자
    "bsns_year": "2024",
    "reprt_code": "11013"     # 사업보고서
}

response = requests.get(url, params=params)
data = response.json()

print(data)