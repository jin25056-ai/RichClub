import os
import glob
import joblib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def run_simulation(df_2026, model, name, is_clf, label_map, feature_cols, result_dir):
    df_test = df_2026.copy()
    
    # ⚡ [긴급 교정] 원본 데이터에 포함된 기존 ma5 컬럼이 있으면 삭제하여 충돌을 막습니다.
    if 'ma5' in df_test.columns:
        df_test = df_test.drop(columns=['ma5'])

    # ⚡ [수정] 수치형 정형화 수행
    for col in feature_cols:
        if col in df_test.columns:
            df_test[col] = pd.to_numeric(df_test[col], errors='coerce')
        else:
            # ⚡ 만약 2026년 데이터에 학습 당시 피처가 누락되었다면 0으로 채워 컬럼을 강제 생성
            df_test[col] = 0.0
            
    df_test[feature_cols] = df_test[feature_cols].fillna(0)
    
    # ⚡ [핵심 교정] 모델이 학습했을 때와 완전히 일치하는 57개 피처 데이터셋 구성 (순서 일치 필수)
    df_test['ticker'] = df_test['stk_cd']
    
    # ⚡ [교정 1] 데이터를 먼저 정렬하고 인덱스를 완전히 고정(reset_index)합니다.
    df_test = df_test.sort_values(by=['ticker', 'date']).reset_index(drop=True)
    
    # ⚡ [교정 2] 순수하게 정렬된 상태에서 5일 이동평균선을 올바르게 계산합니다.
    df_test['ma5'] = df_test.groupby('ticker')['close'].transform(lambda x: x.rolling(window=5, min_periods=1).mean())
    
    # ⚡ [교정 3] 정렬이 완전히 끝난 df_test를 기준으로 예측용 X_test를 추출합니다.
    X_test = df_test[feature_cols]
    has_vp = 'above_max_volume_profile' in df_test.columns
    
    # ⚡ [교정 4] 1:1로 매핑이 완벽해진 인덱스를 바탕으로 모델 예측 및 매수 조건을 정의합니다.
    if is_clf:
        buy_idx = label_map['label_to_idx'].get(1, 1) 
        df_test['pred_score'] = model.predict_proba(X_test)[:, buy_idx]
        
        if has_vp:
            trigger_condition = (df_test['pred_score'] > 0.70) & (df_test['above_max_volume_profile'] == 1) & (df_test['target'] != 3)
        else:
            trigger_condition = (df_test['pred_score'] > 0.70) & (df_test['target'] != 3)
    else:
        df_test['pred_score'] = model.predict(X_test)
        if has_vp:
            trigger_condition = (df_test['pred_score'] > 0.05) & (df_test['above_max_volume_profile'] == 1) & (df_test['target'] != 3)
        else:
            trigger_condition = (df_test['pred_score'] > 0.05) & (df_test['target'] != 3)
        
    df_test['ticker'] = df_test['stk_cd']
    df_test = df_test.sort_values(by=['ticker', 'date']).reset_index(drop=True)
    df_test['ma5'] = df_test.groupby('ticker')['close'].transform(lambda x: x.rolling(window=5, min_periods=1).mean())
    # 백테스팅 환경 초기화
    init_seed = 10000000
    cash = init_seed
    max_slots = 4
    portfolio = {}
    trade_logs = []
    buy_count = 0; sell_count = 0; win_count = 0; target_match_count = 0
    
    unique_dates = sorted(df_test['date'].unique())
    
    for current_date in unique_dates:
        day_data = df_test[df_test['date'] == current_date]
        
        # [매도 프로세스] 5일선 이탈 시 청산
        tickers_to_sell = []
        for ticker, info in list(portfolio.items()):
            stock_today = day_data[day_data['ticker'] == ticker]
            if not stock_today.empty:
                current_price = stock_today['close'].values[0]
                ma5_val = stock_today['ma5'].values[0]
                if np.isnan(ma5_val): ma5_val = current_price
                
                if current_price < ma5_val:
                    sell_amount = current_price * info['shares']
                    cash += sell_amount
                    profit = sell_amount - (info['buy_price'] * info['shares'])
                    roi = (current_price / info['buy_price'] - 1) * 100
                    sell_count += 1
                    if profit > 0: win_count += 1
                    
                    trade_logs.append({
                        'ticker': ticker, 'buy_date': info['buy_date'], 'sell_date': current_date,
                        'buy_price': info['buy_price'], 'sell_price': current_price,
                        'profit': profit, 'roi': roi, 'status': 'SELL'
                    })
                    tickers_to_sell.append(ticker)
        for t in tickers_to_sell: del portfolio[t]
        
        # [매수 프로세스] 진입
        buy_candidates = day_data[trigger_condition].sort_values(by='pred_score', ascending=False)
        available_slots = max_slots - len(portfolio)
        
        if available_slots > 0 and not buy_candidates.empty:
            allocated_cash = cash / available_slots
            for _, row in buy_candidates.iterrows():
                ticker = row['ticker']
                if len(portfolio) < max_slots and ticker not in portfolio:
                    actual_cash = min(allocated_cash, cash)
                    if actual_cash < 10000: continue
                    
                    buy_price = row['close']
                    shares = actual_cash / buy_price
                    cash -= actual_cash
                    portfolio[ticker] = {'buy_price': buy_price, 'shares': shares, 'buy_date': current_date}
                    buy_count += 1
                    
                    high_price = row['high_pric'] if 'high_pric' in row else buy_price
                    if high_price >= (buy_price * 1.15):
                        target_match_count += 1
                        
    # 만기 강제 청산
    if unique_dates:
        last_date = unique_dates[-1]
        last_day_data = df_test[df_test['date'] == last_date]
        for ticker, info in list(portfolio.items()):
            stock_today = last_day_data[last_day_data['ticker'] == ticker]
            current_price = stock_today['close'].values[0] if not stock_today.empty else info['buy_price']
            sell_amount = current_price * info['shares']
            cash += sell_amount
            profit = sell_amount - (info['buy_price'] * info['shares'])
            roi = (current_price / info['buy_price'] - 1) * 100
            sell_count += 1
            if profit > 0: win_count += 1
            trade_logs.append({
                'ticker': ticker, 'buy_date': info['buy_date'], 'sell_date': last_date,
                'buy_price': info['buy_price'], 'sell_price': current_price,
                'profit': profit, 'roi': roi, 'status': 'EXPIRED_CLEAR'
            })
        
    final_asset = cash
    total_profit_amt = final_asset - init_seed
    total_roi = (final_asset / init_seed - 1) * 100
    win_rate = (win_count / sell_count * 100) if sell_count > 0 else 0
    
    print(f"\n================ [{name} 모델 기반 2026년 시뮬레이션 결과] ================")
    print(f"1. 초기 투자 자산  : {init_seed:,.0f} 원")
    print(f"2. 최종 추정 자산  : {final_asset:,.0f} 원")
    print(f"3. 누적 수익 금액  : {total_profit_amt:,.0f} 원 (수익률: {total_roi:.2f} %)")
    print(f"4. 총 매매 거래    : 총 {buy_count}회 매수 / 총 {sell_count}회 청산 완료")
    print(f"5. 모의 매매 승률  : {win_rate:.2f} %")
    print(f"6. 급등 조건 적중  : 예측 확률 진입 후 15% 이상 스파이크 돌파 {target_match_count}회 발생")
    print("====================================================================")
    
    if trade_logs:
        trade_df = pd.DataFrame(trade_logs)
        output_log_path = os.path.join(result_dir, f'trading_simulation_{name}_result_2026.csv')
        trade_df.to_csv(output_log_path, index=False, encoding='cp949')
        print(f"▶ 상세 매매 일지가 저장되었습니다: {output_log_path}")
        
    return total_roi, win_rate, buy_count

if __name__ == '__main__':
    RAW_DIR = r"C:\Users\human3_04\Desktop\richclub\modelCombo\rawdata"
    MODEL_DIR = r"C:\Users\human3_04\Desktop\richclub\modelCombo\train_pklFile"
    RESULT_DIR = r"C:\Users\human3_04\Desktop\richclub\modelCombo\test_result"
    
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    file_2026 = os.path.join(RAW_DIR, "engineered_stock_data_2026.csv")
    label_map_path = os.path.join(MODEL_DIR, "target_label_map.pkl")
    feature_cols_path = os.path.join(MODEL_DIR, "model_features.pkl")
    
    if not os.path.exists(file_2026):
        raise FileNotFoundError(f"시뮬레이션할 2026년 파일이 없습니다: {file_2026}")
    if not os.path.exists(label_map_path) or not os.path.exists(feature_cols_path):
        raise FileNotFoundError("라벨 매퍼 또는 피처 목록 파일(.pkl)이 존재하지 않습니다. 먼저 학습을 다시 실행해 주세요.")
        
    print("▶ 대형 매물대 및 침체필터 통합형 2026년 포트폴리오 백테스팅 가동...")
    df_2026 = pd.read_csv(file_2026, encoding='cp949', dtype={'stk_cd': str})
    label_map = joblib.load(label_map_path)
    feature_cols = joblib.load(feature_cols_path) # ⚡ 저장된 57개 피처 리스트 로드
    
    model_files = glob.glob(os.path.join(MODEL_DIR, "*.pkl"))
    results_summary = []
    
    for model_path in model_files:
        name = os.path.basename(model_path).replace(".pkl", "")
        if name in ["target_label_map", "model_features"]: 
            continue
            
        model = joblib.load(model_path)
        is_clf = "classifier" in name
        
        roi, win_rate, trades = run_simulation(df_2026, model, name, is_clf, label_map, feature_cols, RESULT_DIR)
        results_summary.append({'Model': name, 'ROI (%)': roi, 'Win Rate (%)': win_rate, 'Total Trades': trades})
        
    summary_df = pd.DataFrame(results_summary)
    print("\n================== [2026년 최종 통합 백테스트 요약 결과표] ==================")
    print(summary_df.to_string(index=False))
    print("=========================================================================")