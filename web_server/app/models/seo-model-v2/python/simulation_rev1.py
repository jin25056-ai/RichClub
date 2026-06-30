import os
import glob
import joblib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def run_simulation(df_2026, model, name, is_clf, label_map, feature_cols, result_dir):
    df_test = df_2026.copy()
    
    if 'ma5' in df_test.columns:
        df_test = df_test.drop(columns=['ma5'])

    for col in feature_cols:
        if col in df_test.columns:
            df_test[col] = pd.to_numeric(df_test[col], errors='coerce')
        else:
            df_test[col] = 0.0
            
    df_test[feature_cols] = df_test[feature_cols].fillna(0)
    
    df_test['ticker'] = df_test['stk_cd']
    df_test = df_test.sort_values(by=['ticker', 'date']).reset_index(drop=True)
    df_test['ma5'] = df_test.groupby('ticker')['close_pric'].transform(lambda x: x.rolling(window=5, min_periods=1).mean())
    
    X_test = df_test[feature_cols]
    has_vp = 'above_max_volume_profile' in df_test.columns
    
    if is_clf:
        buy_idx = label_map['label_to_idx'].get(1, 1) 
        df_test['pred_score'] = model.predict_proba(X_test)[:, buy_idx]
        trigger_condition = (df_test['pred_score'] > 0.70) & (df_test['target'] != 3)
        if has_vp:
            trigger_condition = trigger_condition & (df_test['above_max_volume_profile'] == 1)
    else:
        df_test['pred_score'] = model.predict(X_test)
        trigger_condition = (df_test['pred_score'] > 0.05) & (df_test['target'] != 3)
        if has_vp:
            trigger_condition = trigger_condition & (df_test['above_max_volume_profile'] == 1)
        
    df_test['is_trigger'] = trigger_condition

    # 백테스팅 환경 초기화
    init_seed = 10000000  # 1,000만 원
    cash = init_seed
    max_slots = 4
    portfolio = {}
    trade_logs = []
    buy_count = 0; sell_count = 0; win_count = 0; target_match_count = 0
    total_shares_bought = 0  
    
    unique_dates = sorted(df_test['date'].unique())
    
    for current_date in unique_dates:
        day_data = df_test[df_test['date'] == current_date].drop_duplicates(subset=['ticker'])
        
        # ----------------------------------------------------
        # [1] 매도 프로세스
        # ----------------------------------------------------
        tickers_to_sell = []
        for ticker, info in list(portfolio.items()):
            stock_today = day_data[day_data['ticker'] == ticker]
            if not stock_today.empty:
                current_price = stock_today['close_pric'].values[0]
                ma5_val = stock_today['ma5'].values[0]
                if np.isnan(ma5_val): ma5_val = current_price
                
                if current_price < ma5_val:
                    sell_total_amt = current_price * info['shares']
                    cash += sell_total_amt
                    
                    profit = sell_total_amt - info['buy_total_amt']
                    roi = (current_price / info['buy_price'] - 1) * 100
                    sell_count += 1
                    if profit > 0: win_count += 1
                    
                    # ⚡ 매도 로그 기록 (실제 거래일 기준)
                    trade_logs.append({
                        'log_date': current_date, # 정렬용 실제 액션 날짜
                        'ticker': ticker, 
                        'status': 'SELL',
                        'buy_date': info['buy_date'], 
                        'sell_date': current_date,
                        'buy_price': info['buy_price'], 
                        'sell_price': current_price,
                        'shares': info['shares'],  
                        'buy_total_amt': info['buy_total_amt'], 
                        'sell_total_amt': sell_total_amt,       
                        'profit': profit, 
                        'roi': roi, 
                        'current_cash_balance': cash
                    })
                    tickers_to_sell.append(ticker)
                    
        for t in tickers_to_sell: 
            del portfolio[t]
        
        # ----------------------------------------------------
        # [2] 매수 프로세스
        # ----------------------------------------------------
        buy_candidates = day_data[day_data['is_trigger'] == True].sort_values(by='pred_score', ascending=False)
        
        for _, row in buy_candidates.iterrows():
            available_slots = max_slots - len(portfolio)
            if available_slots <= 0: 
                break
                
            ticker = row['ticker']
            if ticker not in portfolio:
                allocated_cash = cash / available_slots
                if allocated_cash < 10000: 
                    continue
                
                buy_price = row['close_pric']
                shares = int(allocated_cash // buy_price)
                if shares <= 0: 
                    continue  
                
                buy_total_amt = buy_price * shares
                cash -= buy_total_amt
                
                portfolio[ticker] = {
                    'buy_price': buy_price, 
                    'shares': shares, 
                    'buy_date': current_date,
                    'buy_total_amt': buy_total_amt
                }
                
                # ⚡ [교정] 매수할 때도 통장 내역처럼 로그를 즉시 남깁니다.
                trade_logs.append({
                    'log_date': current_date, # 정렬용 실제 액션 날짜
                    'ticker': ticker, 
                    'status': 'BUY',
                    'buy_date': current_date, 
                    'sell_date': '',
                    'buy_price': buy_price, 
                    'sell_price': 0,
                    'shares': shares,  
                    'buy_total_amt': buy_total_amt, 
                    'sell_total_amt': 0,       
                    'profit': 0, 
                    'roi': 0, 
                    'current_cash_balance': cash # 돈이 빠져나간 직후의 잔액
                })
                
                buy_count += 1
                total_shares_bought += shares  
                
                high_price = row['high_pric'] if 'high_pric' in row else buy_price
                if high_price >= (buy_price * 1.15):
                    target_match_count += 1
                        
    # ----------------------------------------------------
    # [3] 만기 강제 청산
    # ----------------------------------------------------
    if unique_dates:
        last_date = unique_dates[-1]
        last_day_data = df_test[df_test['date'] == last_date].drop_duplicates(subset=['ticker'])
        
        for ticker, info in list(portfolio.items()):
            stock_today = last_day_data[last_day_data['ticker'] == ticker]
            current_price = stock_today['close_pric'].values[0] if not stock_today.empty else info['buy_price']
            
            sell_total_amt = current_price * info['shares']
            cash += sell_total_amt
            
            profit = sell_total_amt - info['buy_total_amt']
            roi = (current_price / info['buy_price'] - 1) * 100
            sell_count += 1
            if profit > 0: win_count += 1
            
            trade_logs.append({
                'log_date': last_date,
                'ticker': ticker, 
                'status': 'EXPIRED_CLEAR',
                'buy_date': info['buy_date'], 
                'sell_date': last_date,
                'buy_price': info['buy_price'], 
                'sell_price': current_price,
                'shares': info['shares'],  
                'buy_total_amt': info['buy_total_amt'],
                'sell_total_amt': sell_total_amt,
                'profit': profit, 
                'roi': roi, 
                'current_cash_balance': cash
            })
        portfolio.clear()
        
    final_asset = cash
    total_profit_amt = final_asset - init_seed
    total_roi = (final_asset / init_seed - 1) * 100
    win_rate = (win_count / sell_count * 100) if sell_count > 0 else 0
    
    print(f"\n================ [{name} 모델 기반 2026년 시뮬레이션 결과] ================")
    print(f"1. 초기 투자 자산  : {init_seed:,.0f} 원")
    print(f"2. 최종 추정 자산  : {final_asset:,.0f} 원")
    print(f"3. 누적 수익 금액  : {total_profit_amt:,.0f} 원 (수익률: {total_roi:.2f} %)")
    print("====================================================================")
    
    if trade_logs:
        trade_df = pd.DataFrame(trade_logs)
        
        # ⚡ [핵심 교정] 모든 BUY / SELL 로그를 실제 일어난 날짜('log_date') 순서대로 정렬합니다.
        trade_df = trade_df.sort_values(by=['log_date', 'status'], ascending=[True, False]).reset_index(drop=True)
        
        column_order = ['log_date', 'ticker', 'status', 'buy_date', 'sell_date', 'buy_price', 'sell_price', 'shares', 'buy_total_amt', 'sell_total_amt', 'profit', 'roi', 'current_cash_balance']
        trade_df = trade_df[column_order]
        
        output_log_path = os.path.join(result_dir, f'trading_simulation_{name}_result_2026.csv')
        trade_df.to_csv(output_log_path, index=False, encoding='utf-8-sig')
        print(f"▶ 상세 매매 일지가 저장되었습니다: {output_log_path}")
        
    return total_roi, win_rate, buy_count, total_shares_bought

if __name__ == '__main__':
    RAW_DIR = r"C:\Users\human3_04\Desktop\richclub\combotest\rawdata"
    MODEL_DIR = r"C:\Users\human3_04\Desktop\richclub\combotest\train_pklFile"
    RESULT_DIR = r"C:\Users\human3_04\Desktop\richclub\combotest\test_result"
    
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    file_2026 = os.path.join(RAW_DIR, "engineered_stock_data_2026.csv")
    label_map_path = os.path.join(MODEL_DIR, "target_label_map.pkl")
    feature_cols_path = os.path.join(MODEL_DIR, "model_features.pkl")
    
    if not os.path.exists(file_2026):
        raise FileNotFoundError(f"시뮬레이션할 2026년 파일이 없습니다: {file_2026}")
    if not os.path.exists(label_map_path) or not os.path.exists(feature_cols_path):
        raise FileNotFoundError("라벨 매퍼 또는 피처 목록 파일(.pkl)이 존재하지 않습니다. 먼저 학습을 다시 실행해 주세요.")
        
    print("▶ 대형 매물대 및 침체필터 통합형 2026년 포트폴리오 백테스팅 가동...")
    df_2026 = pd.read_csv(file_2026, encoding='utf-8-sig', dtype={'stk_cd': str})
    label_map = joblib.load(label_map_path)
    feature_cols = joblib.load(feature_cols_path) 
    
    model_files = glob.glob(os.path.join(MODEL_DIR, "*.pkl"))
    results_summary = []
    
    for model_path in model_files:
        name = os.path.basename(model_path).replace(".pkl", "")
        if name in ["target_label_map", "model_features"]: 
            continue
            
        model = joblib.load(model_path)
        is_clf = "classifier" in name
        
        roi, win_rate, trades, shares = run_simulation(df_2026, model, name, is_clf, label_map, feature_cols, RESULT_DIR)
        results_summary.append({
            'Model': name, 
            'ROI (%)': roi, 
            'Win Rate (%)': win_rate, 
            'Total Trades': trades,
            'Total Shares': int(shares)  # ⚡ [변경] 요약 표에서도 소수점 없이 정수로 매핑
        })
        
    summary_df = pd.DataFrame(results_summary)
    print("\n================== [2026년 최종 통합 백테스트 요약 결과표] ==================")
    print(summary_df.to_string(index=False))
    print("=========================================================================")