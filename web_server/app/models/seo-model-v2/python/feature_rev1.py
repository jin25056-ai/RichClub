import pandas as pd
import numpy as np
import os
import warnings

# SettingWithCopyWarning 방지
warnings.filterwarnings('ignore', message='.*SettingWithCopy.*')

def clean_and_convert_numeric(series):
    """부호 및 쌍따옴표 제거 후 절대값 처리 (저가 마이너스 방어용)"""
    val = pd.to_numeric(series.astype(str).str.replace('"', '').str.replace('+', '').str.strip(), errors='coerce')
    return np.abs(val)

def add_volume_profile_vectorized(df, window=20, num_bins=5):
    """대용량 종목 데이터를 처리하는 매물대 지지/저항 생성기 (원본 로직 유지)"""
    high_arr = df['high_pric'].values if 'high_pric' in df.columns else df['close'].values
    low_arr = df['low_pric'].values if 'low_pric' in df.columns else df['close'].values
    vol_arr = df['volume'].values if 'volume' in df.columns else np.ones(len(df))
    
    vp_prices = np.full(len(df), np.nan)
    stk_boundaries = np.where(df['stk_cd'].values[:-1] != df['stk_cd'].values[1:])[0] + 1
    stk_boundaries = np.insert(stk_boundaries, 0, 0)
    stk_boundaries = np.append(stk_boundaries, len(df))
    
    for b in range(len(stk_boundaries)-1):
        start_idx = stk_boundaries[b]
        end_idx = stk_boundaries[b+1]
        
        for i in range(start_idx, end_idx):
            w_start = max(start_idx, i - window + 1)
            w_end = i + 1
            
            sub_high = high_arr[w_start:w_end]
            sub_low = low_arr[w_start:w_end]
            sub_vol = vol_arr[w_start:w_end]
            
            if len(sub_high) == 0:
                continue
                
            h_max = np.max(sub_high)
            l_min = np.min(sub_low)
            
            if h_max == l_min:
                vp_prices[i] = h_max
                continue
                
            bins = np.linspace(l_min, h_max, num_bins + 1)
            bin_vols = np.zeros(num_bins)
            
            for j in range(len(sub_high)):
                h_j = sub_high[j]
                l_j = sub_low[j]
                v_j = sub_vol[j]
                
                overlap_min = np.maximum(bins[:-1], l_j)
                overlap_max = np.minimum(bins[1:], h_j)
                overlap_len = np.maximum(0, overlap_max - overlap_min)
                
                total_len = h_j - l_j
                if total_len > 0:
                    weight = overlap_len / total_len
                    bin_vols += weight * v_j
                else:
                    idx = np.searchsorted(bins, l_j) - 1
                    idx = np.clip(idx, 0, num_bins - 1)
                    bin_vols[idx] += v_j
                    
            max_bin_idx = np.argmax(bin_vols)
            vp_prices[i] = (bins[max_bin_idx] + bins[max_bin_idx+1]) / 2.0
            
    df['poc_price'] = vp_prices
    # 매물대 계산 초기 구간 결측치는 당일 종가로 메꿔 행 탈락 방지
    df['poc_price'] = df['poc_price'].fillna(df['close'])
    return df

def add_all_features_modified(df):
    """전체 피처 엔지니어링 수행 파이프라인 (종목별 Groupby 적용 안전화)"""
    grouped = df.groupby('stk_cd')
    
    # 이동평균선 계산 (min_periods=1로 설정하여 초기 데이터 패스 방지)
    df['ma5'] = grouped['close'].transform(lambda x: x.rolling(window=5, min_periods=1).mean())
    df['ma20'] = grouped['close'].transform(lambda x: x.rolling(window=20, min_periods=1).mean())
    df['ma60'] = grouped['close'].transform(lambda x: x.rolling(window=60, min_periods=1).mean())
    
    # MACD 지표 연산
    def calc_macd_signals(sub_df):
        sub_df = sub_df.copy()
        ema12 = sub_df['close'].ewm(span=12, adjust=False).mean()
        ema26 = sub_df['close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        return pd.DataFrame({'macd': macd, 'macd_sig': signal, 'macd_hist': hist}, index=sub_df.index)
        
    macd_df = grouped.apply(calc_macd_signals).reset_index(level=0, drop=True)
    df[['macd', 'macd_sig', 'macd_hist']] = macd_df[['macd', 'macd_sig', 'macd_hist']]
    
    # MACD 초기 NaN 값 방어
    df[['macd', 'macd_sig', 'macd_hist']] = df[['macd', 'macd_sig', 'macd_hist']].fillna(0)
    
    # 매물대 지표 추가
    df = add_volume_profile_vectorized(df, window=20, num_bins=5)
    
    return df

def generate_labeled_target(df):
    """[최종 수정본] 원본 행 데이터 유지 및 완벽한 타겟 구분 버전 (-1은 관망/홀딩 상태로 유지)"""
    df = df.copy()
    grouped = df.groupby('stk_cd')
    
    db_macd = df['macd']
    db_macd_signal = df['macd_sig']
    
    cond_yang_bong = df['close'] > df['open_pric']
    cond_eum_bong = df['close'] < df['open_pric']
    
    ma5_prev = grouped['ma5'].shift(1).fillna(df['ma5'])
    ma20_prev = grouped['ma20'].shift(1).fillna(df['ma20'])
    ma60_prev = grouped['ma60'].shift(1).fillna(df['ma60'])
    close_prev = grouped['close'].shift(1).fillna(df['close'])
    
    ma5_20_prev_ratio = ma5_prev / ma20_prev
    cond_ma5_20_gc = (df['ma5'] > df['ma20']) & (ma5_20_prev_ratio <= 1)
    cond_ma5_20_dc = (df['ma5'] < df['ma20']) & (ma5_20_prev_ratio >= 1)
    
    cond_ma60_above = df['close'] >= df['ma60']
    close_ma60_prev_ratio = close_prev / ma60_prev
    cond_ma60_gc = (df['close'] >= df['ma60']) & (close_ma60_prev_ratio < 1)
    cond_ma60_filter = cond_ma60_above | cond_ma60_gc
    
    cond_macd_pure = db_macd > db_macd_signal
    macd_prev = grouped['macd'].shift(1).fillna(df['macd'])
    cond_macd_rising = db_macd > macd_prev
    cond_macd_total = cond_macd_pure & cond_macd_rising
    
    cond_stoch_pure = df['stoch_k'] > df['stoch_d'] if 'stoch_k' in df.columns else True
    cond_obv_rising = df['obv'] > grouped['obv'].shift(1) if 'obv' in df.columns else True
    cond_ma5_rising = df['ma5'] > ma5_prev
    cond_stoch_k_rising = df['stoch_k'] > grouped['stoch_k'].shift(1) if 'stoch_k' in df.columns else True
    
    watch_signal = cond_ma5_rising & cond_macd_total & cond_stoch_k_rising & cond_obv_rising
    
    cond_sp500_bear_market = df['sp500'] < df['sp500_ma20'] if 'sp500' in df.columns else False
    cond_vix_panic = df['vix_change'] >= 0.10 if 'vix_change' in df.columns else False

    cond_ma60_falling = df['ma60'] < ma60_prev
    cond_slump_zone = (df['ma5'] < df['ma60']) & (df['ma20'] < df['ma60']) & cond_ma60_falling

    # 레이블 초기화 (-1: 매매 없음 / 기존 보유종목 홀딩 상태)
    df['target'] = -1

    # 1. 침체 구간 필터링 (target = 3)
    df.loc[cond_slump_zone, 'target'] = 3

    # 2. 관망 필터링 (target = 2)
    watch_mask = watch_signal & (~cond_slump_zone)
    df.loc[watch_mask, 'target'] = 2

    # 3. 매수 필터링 (target = 1)
    base_buy_signal = cond_yang_bong & cond_macd_total & cond_stoch_pure & cond_ma5_20_gc & cond_ma60_filter & cond_obv_rising
    buy_mask = base_buy_signal & (~cond_sp500_bear_market) & (~cond_slump_zone)
    df.loc[buy_mask, 'target'] = 1

    # 4. 매도 필터링 (target = 0) -> 최우선 덮어쓰기
    if 'stoch_k' in df.columns:
        is_dead_cross = (df['stoch_k'] < df['stoch_d']) & (grouped['stoch_k'].shift(1) >= grouped['stoch_d'].shift(1))
    else:
        is_dead_cross = cond_ma5_20_dc | (df['macd'] < df['macd_sig'])
        
    cond_vol_rising = df['volume'] > grouped['volume'].shift(1)
    sell_mask = (is_dead_cross & cond_vol_rising & cond_eum_bong) | cond_vix_panic
    df.loc[sell_mask, 'target'] = 0

    # 미래 수익률 연산 부분 (dropna 없이 fillna 처리로 보완)
    def calc_future_returns(group):
        close = group['close']
        res = {}
        for days in [1, 3, 5, 10]:
            res[f'reg_return_{days}d'] = (close.shift(-days).rolling(window=days, min_periods=1).max() / close) - 1
            res[f'reg_mdd_{days}d'] = (close.shift(-days).rolling(window=days, min_periods=1).min() / close) - 1
        return pd.DataFrame(res, index=group.index)
        
    future_returns = grouped.apply(calc_future_returns).reset_index(level=0, drop=True)
    for days in [1, 3, 5, 10]:
        df[f'reg_return_{days}d'] = future_returns[f'reg_return_{days}d'].fillna(0)
        df[f'reg_mdd_{days}d'] = future_returns[f'reg_mdd_{days}d'].fillna(0)
        df[f'class_win_{days}d'] = (df[f'reg_return_{days}d'] >= 0.05).astype(int)
        df[f'class_lose_{days}d'] = (df[f'reg_mdd_{days}d'] <= -0.03).astype(int)

    # ⚡ [중요 수정] 데이터 증발을 일으키던 행 차단 구문 필터 제거!
    # df = df[df['target'] != -1].copy()  <-- 이 구문을 지워 날짜가 온전히 유지됩니다.
    return df

if __name__ == '__main__':
    RAW_DIR = r"C:\Users\human3_04\Desktop\richclub\modelCombo\rawdata"
    target_years = [2021, 2022, 2023, 2024, 2025, 2026]
    
    for year in target_years:
        input_filename = f'stock_data_{year}.csv'
        input_path = os.path.join(RAW_DIR, input_filename)
        
        if os.path.exists(input_path):
            print(f"\n=== {year}년도 데이터 완전성 보존 파이프라인 엔지니어링 시작 ===")
            df = pd.read_csv(input_path, encoding='cp949')
            
            # 정형 수치 컬럼 정제
            numeric_cols = ['close', 'volume', 'open_pric', 'high_pric', 'low_pric', 'trde_qty']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = clean_and_convert_numeric(df[col])
            
            # 시계열 순서 강제 정렬 (종목코드별 -> 날짜별 오름차순)
            df = df.sort_values(by=['stk_cd', 'date']).reset_index(drop=True)
            
            # 파이프라인 연산 수행 (이제 날짜 누락 없음)
            df = add_all_features_modified(df)
            df = generate_labeled_target(df)
            
            # 최종 저장
            output_filename = f'engineered_stock_data_{year}.csv'
            output_path = os.path.join(RAW_DIR, output_filename)
            df.to_csv(output_path, index=False, encoding='cp949')
            print(f"=== {year}년도 처리 완료! 행 유실 없음 ➡️ 저장 완료: {len(df)} 행 ===")
        else:
            print(f"파일을 찾을 수 없습니다: {input_path}")