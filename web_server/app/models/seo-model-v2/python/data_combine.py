import os
import re
import pandas as pd

def merge_data(year):
    """
    지정한 연도의 키움 데이터(수급)와 공공 데이터(가격/거래량)를 안전하게 정제 후 병합하는 함수
    """
    # 1. 절대 경로 직접 고정 정의
    RAW_DATA_DIR = r"C:\Users\human3_04\Desktop\richclub\급등주포착모델\raw_data"
    OUTPUT_DIR = r"C:\Users\human3_04\Desktop\richclub\modelCombo\rawdata"
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    kiwoom_filename = f'kiwoom_data_{year}.csv'
    price_filename = f'price_filtered_{year}.csv'
    
    kiwoom_path = os.path.join(RAW_DATA_DIR, kiwoom_filename)
    price_path = os.path.join(RAW_DATA_DIR, price_filename)
    
    if not os.path.exists(kiwoom_path) or not os.path.exists(price_path):
        print(f"⚠️ [{year}년도] 병합 실패: 원본 파일이 존재하지 않습니다.\n   - 경로 확인: {RAW_DATA_DIR}")
        return
        
    print(f"\n=== 🛠️ [{year}년도] 데이터 정제 및 결합 시작 ===")
    
    # 2. 가격 데이터 로드 및 콤마/쌍따옴표 오염 파싱 제어
    # 공공데이터 csv 내부가 통째로 따옴표 처리되어 있어 분리 처리가 필요합니다.
    try:
        price_df = pd.read_csv(price_path, encoding='cp949', quotechar='"')
    except Exception:
        price_df = pd.read_csv(price_path, encoding='utf-8', quotechar='"')
        
    # 만약 데이터가 한 컬럼으로 뭉쳐 들어왔을 경우 분리 파싱 강제 적용
    if len(price_df.columns) == 1:
        col_name = price_df.columns[0]
        price_df = price_df[col_name].str.split(',', expand=True)
        # 헤더 복원 및 클리닝
        headers = col_name.replace('"', '').split(',')
        price_df.columns = headers[:len(price_df.columns)]
    
    # 컬럼명 앞뒤 공백 및 잔여 쌍따옴표 완전 제거
    price_df.columns = price_df.columns.str.strip().str.replace('"', '')
    
    # 공공데이터 컬럼명을 시스템 컬럼명 구조로 매핑 전환
    rename_dict = {'basDt': 'date', 'srtnCd': 'stk_cd', 'clpr': 'close', 'trqu': 'volume', 'trPrc': 'amount'}
    price_df = price_df.rename(columns=rename_dict)
    
    # 3. 키움 데이터 로드
    try:
        kiwoom_df = pd.read_csv(kiwoom_path, encoding='cp949', quotechar='"')
    except Exception:
        kiwoom_df = pd.read_csv(kiwoom_path, encoding='utf-8', quotechar='"')
        
    kiwoom_df.columns = kiwoom_df.columns.str.strip().str.replace('"', '')
    
    # 4. [핵심] 날짜(date) 데이터 정형화 (특수문자 걷어내고 순수 숫자 8자리로 매칭)
    price_df['date'] = price_df['date'].astype(str).str.replace(r'[^0-9]', '', regex=True).str.strip()
    kiwoom_df['date'] = kiwoom_df['date'].astype(str).str.replace(r'[^0-9]', '', regex=True).str.strip()
    
    # 5. [핵심] 종목코드(stk_cd) 특수문자/알파벳 제거 후 6자리 패딩 공정 통일
    def clean_stock_code(code):
        if pd.isna(code):
            return None
        code_str = str(code).replace('"', '').strip()
        # 알파벳(예: A005930의 A)이 섞여있다면 제거하고 숫자만 남김
        numbers = re.sub(r'[^0-9]', '', code_str)
        return numbers.zfill(6) if numbers else None

    price_df['stk_cd'] = price_df['stk_cd'].apply(clean_stock_code)
    kiwoom_df['stk_cd'] = kiwoom_df['stk_cd'].apply(clean_stock_code)
    
    # 결측치 축 드롭
    price_df = price_df.dropna(subset=['date', 'stk_cd'])
    kiwoom_df = kiwoom_df.dropna(subset=['date', 'stk_cd'])
    
    # 중복 데이터 제거 방어선
    price_df = price_df.drop_duplicates(subset=['date', 'stk_cd'])
    kiwoom_df = kiwoom_df.drop_duplicates(subset=['date', 'stk_cd'])
    
    print(f"   - 정제 완료된 가격 데이터: {len(price_df)}건")
    print(f"   - 정제 완료된 수급 데이터: {len(kiwoom_df)}건")
    
    # 6. 데이터 최종 병합 (교집합 Inner Join)
    merged_df = pd.merge(price_df, kiwoom_df, on=['date', 'stk_cd'], how='inner')
    
    # 7. 주식 분석용 데이터 정렬 (종목별 -> 날짜 오름차순 순서 정렬)
    merged_df = merged_df.sort_values(['stk_cd', 'date']).reset_index(drop=True)
    
    # 8. 최종 결과물 저장
    output_filename = f'stock_data_{year}.csv'
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    merged_df.to_csv(output_path, index=False, encoding='cp949')
    print(f"▶ [{year}년도] 데이터 연계 병합 대성공! (결합 성공 데이터 수: {len(merged_df)}건)")
    print(f"▶ 저장 완료 경로: {output_path}")

if __name__ == '__main__':
    # 2021년부터 2026년까지의 전체 데이터 결합 일괄 순회 구동
    target_years = [2021, 2022, 2023, 2024, 2025, 2026]
    
    for year in target_years:
        merge_data(year)