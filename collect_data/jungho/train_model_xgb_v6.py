import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from sklearn.utils.class_weight import compute_sample_weight

from xgboost import XGBClassifier

# ===== 1. 환경 변수 및 몽고DB 데이터 가져오기 =====
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

raw_df = pd.DataFrame(list(collection.find()))

# ===== 2. 데이터 기본 정제 =====
if '_id' in raw_df.columns:
    raw_df.drop(columns=['_id'], inplace=True)

raw_df.columns = [col.lower() for col in raw_df.columns]

if 'date' in raw_df.columns:
    raw_df['date'] = pd.to_datetime(raw_df['date'])
    raw_df.sort_values('date', ascending=True, inplace=True)
    raw_df.reset_index(drop=True, inplace=True)


# ===== 3. 전처리 및 레이블링 함수 (시장 지표 제거) =====
def build_dataset_by_rules(df):
    df = df.copy()

    # 1) 이동평균선 계산
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma60'] = df['close'].rolling(window=60).mean()

    # 2) MACD 및 시그널 계산
    db_macd = df['macd']
    db_macd_signal = db_macd.ewm(span=9, adjust=False).mean()

    # 3) 스토캐스틱 Slow 계산 (%K=12, %D=5)
    low_min = df['low'].rolling(window=12).min()
    high_max = df['high'].rolling(window=12).max()
    fast_k = 100 * ((df['close'] - low_min) / (high_max - low_min))
    df['stoch_k'] = fast_k.rolling(window=3).mean()
    df['stoch_d'] = df['stoch_k'].rolling(window=5).mean()

    # 데드크로스 판별용 직전 값 매핑
    df['stoch_prev_k'] = df['stoch_k'].shift(1)
    df['stoch_prev_d'] = df['stoch_d'].shift(1)

    # 4) OBV 계산
    direction = np.sign(df['close'].diff())
    direction.iloc[0] = 0
    df['obv'] = (direction * df['volume']).cumsum()

    # 5) AI 모델용 파생 Feature 생성
    df['ma5_20_ratio'] = df['ma5'] / df['ma20']
    df['ma20_60_ratio'] = df['ma20'] / df['ma60']
    df['close_ma60_ratio'] = df['close'] / df['ma60']
    df['vol_change'] = df['volume'].pct_change()
    df['macd_change'] = db_macd.diff()
    df['stoch_k_change'] = df['stoch_k'].diff()

    # ===== [기본 구성 조건 정의] =====
    # 캔들 형태 (양봉 / 음봉)
    cond_yang_bong = df['close'] > df['open']
    cond_eum_bong = df['close'] < df['open']

    # 5일선, 20일선 골든크로스 당일 판별
    ma5_20_prev_ratio = df['ma5'].shift(1) / df['ma20'].shift(1)
    cond_ma5_20_gc = (df['ma5'] > df['ma20']) & (ma5_20_prev_ratio <= 1)

    # 60일선 조건 (위에 있거나 상향돌파)
    cond_ma60_above = df['close'] >= df['ma60']
    close_ma60_prev_ratio = df['close'].shift(1) / df['ma60'].shift(1)
    cond_ma60_gc = (df['close'] >= df['ma60']) & (close_ma60_prev_ratio < 1)
    cond_ma60_filter = cond_ma60_above | cond_ma60_gc

    # MACD 조건 (정배열: MACD > Signal AND 상승: 당일 > 전일)
    cond_macd_pure = db_macd > db_macd_signal
    cond_macd_rising = db_macd > db_macd.shift(1)
    cond_macd_total = cond_macd_pure & cond_macd_rising

    # 스토캐스틱 조건 (정배열: K > D)
    cond_stoch_pure = df['stoch_k'] > df['stoch_d']

    # OBV 조건 (상승: 당일 > 전일)
    cond_obv_rising = df['obv'] > df['obv'].shift(1)

    # ===== [관망 조건 정의] =====
    cond_ma5_rising = df['ma5'] > df['ma5'].shift(1)
    cond_stoch_k_rising = df['stoch_k'] > df['stoch_k'].shift(1)

    watch_signal = cond_ma5_rising & cond_macd_total & cond_stoch_k_rising & cond_obv_rising

    # ===== [매수 예외 조건 정의] =====
    # 관망 상태에서 스토캐스틱 슬로우 K선이 과열진입(80 이상 돌파) 시 매수
    cond_stoch_overbought_enter = (df['stoch_k'] >= 80) & (df['stoch_prev_k'] < 80)
    watch_buy_exception = watch_signal & cond_stoch_overbought_enter

    # ===== [레이블링 규칙 적용] =====
    df['target'] = -1

    # 1. 매수 조건 적용 (시장 지표 필터 없이 순수 기술적 신호만)
    base_buy_signal = cond_yang_bong & cond_macd_total & cond_stoch_pure & cond_ma5_20_gc & cond_ma60_filter & cond_obv_rising
    buy_mask = (base_buy_signal.shift(1) == True) | watch_buy_exception
    df.loc[buy_mask, 'target'] = 1

    # 2. 매도 조건 적용 (시장 지표 필터 없이 순수 기술적 신호만)
    is_stoch_dead_cross = (df['stoch_k'] < df['stoch_d']) & (df['stoch_prev_k'] >= df['stoch_prev_d'])
    cond_vol_rising = df['volume'] > df['volume'].shift(1)
    sell_mask = is_stoch_dead_cross & cond_vol_rising & cond_eum_bong
    df.loc[sell_mask, 'target'] = 0

    # 3. 관망 조건 적용
    watch_mask = (df['target'] == -1) & watch_signal
    df.loc[watch_mask, 'target'] = 2

    # 무한대 치환 및 매칭되지 않는 데이터(-1) 탈락 처리
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df = df[df['target'] != -1].copy()
    df.dropna(
        subset=['target', 'ma5_20_ratio', 'vol_change', 'stoch_k', 'obv', 'macd_change'],
        inplace=True
    )

    return df


# 데이터 가공 실행
dataset = build_dataset_by_rules(raw_df)

# 학습용 피처 리스트 (시장 지표 제거 - 순수 기술적 지표만)
feature_cols = [
    'ma5_20_ratio', 'ma20_60_ratio', 'close_ma60_ratio',
    'vol_change', 'macd', 'stoch_k', 'stoch_d', 'obv',
    'macd_change', 'stoch_k_change'
]
X = dataset[feature_cols]
y = dataset['target']

if len(X) < 10:
    print(f"❌ 전략 조건을 충족하는 데이터 샘플이 부족합니다 (현재 수량: {len(X)}개).")
else:
    # ===== 4. 데이터 분할 =====
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    # 데이터 불균형 방지를 위한 가중치 계산
    sample_weights = compute_sample_weight(class_weight='balanced', y=y_train)

    # ===== 5. XGBClassifier 모델 생성 및 학습 =====
    model = XGBClassifier(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=4,
        random_state=42,
        eval_metric='mlogloss'
    )

    model.fit(
        X_train, y_train,
        sample_weight=sample_weights,
        eval_set=[(X_test, y_test)],
        verbose=False
    )

    # ===== 6. 테스트 데이터 예측 및 평가 결과 출력 =====
    y_pred = model.predict(X_test)

    print("-" * 50)
    print(f"🎯 기술적 지표 전용 모델 검증 정확도(Accuracy): {accuracy_score(y_test, y_pred):.4f}")
    print("-" * 50)
    print("[상세 분류 레포트]")
    print(classification_report(y_test, y_pred, target_names=['매도(0)', '매수(1)', '관망(2)'], labels=[0, 1, 2]))

    # 혼동 행렬 시각화
    plt.rc('font', family='Malgun Gothic')
    plt.rc('axes', unicode_minus=False)

    cm = confusion_matrix(y_test, y_pred, labels=[0, 1, 2])

    plt.figure(figsize=(8, 6))
    sns.heatmap(
        cm, annot=True, fmt='d', cmap='Blues',
        xticklabels=['매도 예측(0)', '매수 예측(1)', '관망 예측(2)'],
        yticklabels=['실제 매도(0)', '실제 매수(1)', '실제 관망(2)']
    )

    plt.title('기술적 지표 전용 최종 혼동 행렬', fontsize=14, pad=15)
    plt.xlabel('모델 예측 (Predicted)', fontsize=12, labelpad=10)
    plt.ylabel('실제 상태 (Actual)', fontsize=12, labelpad=10)
    plt.tight_layout()
    plt.show()

    # ===== 7. 전체 데이터에 signal 컬럼 추가 및 통합 CSV 저장 =====
    print("\n" + "=" * 50)
    print("💾 전체 데이터에 signal 컬럼 추가 및 통합 CSV 저장 시작")
    print("=" * 50)

    total_result_df = dataset.loc[X_test.index].copy()

    label_map = {0: '매도', 1: '매수', 2: '관망'}
    total_result_df['signal'] = [label_map[pred] for pred in y_pred]

    name_col = 'stock_name' if 'stock_name' in total_result_df.columns else None
    if not name_col:
        for col in ['name', 'item_name', 'code', 'ticker', 'symbol']:
            if col in total_result_df.columns:
                name_col = col
                break
    if not name_col:
        total_result_df['stock_name'] = '종목'
        name_col = 'stock_name'

    total_result_df['date'] = total_result_df['date'].dt.strftime('%Y-%m-%d')

    front_cols = ['date', name_col, 'close', 'signal']
    remaining_cols = [col for col in total_result_df.columns if col not in front_cols]

    final_csv_df = total_result_df[front_cols + remaining_cols].copy()
    final_csv_df.rename(columns={
        'date': '날짜',
        name_col: '종목명',
        'close': '종가',
        'signal': '시그널'
    }, inplace=True)

    output_filename = 'total_trading_signals.csv'
    final_csv_df.to_csv(output_filename, index=False, encoding='utf-8-sig')

    print(f"📊 [통합 완료] 모든 데이터 뒤에 시그널이 추가되었습니다.")
    print(f"💾 파일 저장 완료 -> [{output_filename}] ({len(final_csv_df)}행)")
    print("=" * 50)

    # ===== 8. AI 모의 투자 시뮬레이션 =====
    print("\n" + "=" * 50)
    print("💰 AI 전략 기반 모의 투자 시뮬레이션")
    print("=" * 50)

    mock_df = dataset.loc[X_test.index].copy()
    mock_df['predicted_signal'] = y_pred

    initial_balance = 10000000  # 원금 1,000만 원
    balance = initial_balance
    active_positions = {}
    total_trades = 0
    win_trades = 0
    asset_history = []
    dates_history = []

    for i in range(len(mock_df)):
        row = mock_df.iloc[i]
        current_date = row['date'].strftime('%Y-%m-%d')
        current_price = row['close']
        signal = row['predicted_signal']
        stock_name = row['stock_name'] if 'stock_name' in row else '종목'

        # 1) 보유 종목 손절/익절/데드크로스 체크
        if stock_name in active_positions:
            pos_info = active_positions[stock_name]
            buy_price = pos_info['buy_price']
            qty = pos_info['qty']
            profit_rate = ((current_price - buy_price) / buy_price) * 100

            is_dead_cross = (signal == 0)
            is_take_profit = (profit_rate >= 5.0)
            is_stop_loss = (profit_rate <= -3.0)

            if is_dead_cross or is_take_profit or is_stop_loss:
                returned_cash = qty * current_price
                balance += returned_cash
                total_trades += 1
                if profit_rate > 0:
                    win_trades += 1
                reason = "익절" if is_take_profit else ("손절" if is_stop_loss else "데드크로스")
                print(f"🔴 [{current_date}] SELL ({reason}) | {stock_name} | 매도가: {int(current_price):,}원 | 수익률: {profit_rate:+.2f}%")
                del active_positions[stock_name]

        # 2) 매수 시그널 처리
        elif signal == 1 and stock_name not in active_positions and balance > 100000:
            invest_amount = balance * 0.20
            balance -= invest_amount
            qty = invest_amount / current_price
            active_positions[stock_name] = {'buy_price': current_price, 'qty': qty}
            print(f"🟩 [{current_date}] BUY  | {stock_name} | 매수가: {int(current_price):,}원 | 투자금: {int(invest_amount):,}원")

        # 3) 총 자산 가치 계산
        current_portfolio_value = balance
        for s_name, pos_info in active_positions.items():
            current_portfolio_value += pos_info['qty'] * current_price

        asset_history.append(current_portfolio_value)
        dates_history.append(row['date'])

    # 최종일 남은 종목 강제 청산
    for s_name, pos_info in list(active_positions.items()):
        balance += pos_info['qty'] * mock_df.iloc[-1]['close']
        total_trades += 1
        profit_rate = ((mock_df.iloc[-1]['close'] - pos_info['buy_price']) / pos_info['buy_price']) * 100
        if profit_rate > 0:
            win_trades += 1

    # ===== 결과 리포트 출력 =====
    final_return_rate = ((balance - initial_balance) / initial_balance) * 100
    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0

    print("\n" + "=" * 50)
    print("📊 AI 모의 투자 최종 성적표")
    print("=" * 50)
    print(f"✔️ 초기 자본금 : {initial_balance:,}원")
    print(f"✔️ 최종 자본금 : {int(balance):,}원")
    print(f"✔️ 누적 수익률 : {final_return_rate:+.2f}%")
    print(f"✔️ 총 거래 횟수: {total_trades}회")
    print(f"✔️ 전략 승률   : {win_rate:.2f}% ({win_trades}승 / {total_trades - win_trades}패)")
    print("=" * 50)

    # ===== 9. 투자 자산 변화 그래프 =====
    plt.figure(figsize=(12, 5))
    plt.plot(dates_history, asset_history, label='내 자산 (AI 전략)', color='dodgerblue', linewidth=2)
    plt.axhline(y=initial_balance, color='tomato', linestyle='--', label='투자 원금')
    plt.title('AI 모의 투자 자산 성장 곡선 (Equity Curve)', fontsize=14, pad=15)
    plt.xlabel('날짜 (Date)', fontsize=12)
    plt.ylabel('자산 총액 (Won)', fontsize=12)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.show()