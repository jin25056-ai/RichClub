import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if '__file__' in locals() else os.getcwd()
RAW_DIR = os.path.join(BASE_DIR, "rawdata")

for year in [2021, 2022, 2023, 2024, 2025]:
    file_path = os.path.join(RAW_DIR, f'stock_data_{year}_engineered_ver1.csv')
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, encoding='cp949')
        print(f"\n📊 [{year}년 데이터 분석]")
        print(f"총 건수: {len(df)}건")
        if len(df) > 0 and 'target' in df.columns:
            print("Target별 데이터 분포:")
            print(df['target'].value_counts(dropna=False))
        else:
            print("⚠️ 데이터가 비어있거나 target 컬럼이 없습니다.")