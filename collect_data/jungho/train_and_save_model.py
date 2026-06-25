"""
train_and_save_model.py
company_signals/*.csv 를 읽어 XGBoost 모델 학습 후 xgb_model.json 저장

실행:
  python train_and_save_model.py

서버(Mac M1)에서 최초 1회 실행, 이후 매주 월요일 자동 재학습
"""
import os
import glob
import logging
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
SIGNALS_DIR = os.path.join(BASE_DIR, 'company_signals')
MODEL_PATH = os.path.join(BASE_DIR, 'xgb_model.json')

FEATURE_COLS = [
    'ma5_20_ratio', 'ma20_60_ratio', 'close_ma60_ratio',
    'vol_change', 'macd', 'stoch_k', 'stoch_d', 'obv',
    'macd_change', 'stoch_k_change', 'sp500_ma_ratio', 'vix_value'
]


def load_csv_data() -> pd.DataFrame:
    files = glob.glob(os.path.join(SIGNALS_DIR, '*.csv'))
    if not files:
        raise FileNotFoundError(f"company_signals/ 폴더에 CSV 없음: {SIGNALS_DIR}")
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, encoding='utf-8-sig')
            df['stock_name'] = os.path.splitext(os.path.basename(f))[0]
            dfs.append(df)
        except Exception as e:
            logger.warning(f"{f} 읽기 실패: {e}")
    combined = pd.concat(dfs, ignore_index=True)
    combined.columns = [c.lower() for c in combined.columns]
    if 'date' in combined.columns:
        combined['date'] = pd.to_datetime(combined['date'])
        combined.sort_values('date', inplace=True)
        combined.reset_index(drop=True, inplace=True)
    logger.info(f"CSV 로드 완료: {len(combined)}행, {len(files)}개 종목")
    return combined


def add_market_data(df: pd.DataFrame) -> pd.DataFrame:
    start = df['date'].min().strftime('%Y-%m-%d')
    end = (df['date'].max() + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    logger.info(f"yfinance 시장 지표 수집 중... ({start} ~ {end})")
    market = yf.download(["^GSPC", "^VIX"], start=start, end=end, interval="1d", progress=False)
    mdf = pd.DataFrame(index=market.index)
    if isinstance(market.columns, pd.MultiIndex):
        mdf['sp500'] = market[('Close', '^GSPC')]
        mdf['vix'] = market[('Close', '^VIX')]
    else:
        mdf['sp500'] = market['Close']
        mdf['vix'] = market['Close']
    mdf.reset_index(inplace=True)
    mdf.rename(columns={'Date': 'date'}, inplace=True)
    mdf['date'] = pd.to_datetime(mdf['date'])
    df = pd.merge_asof(df.sort_values('date'), mdf.sort_values('date'), on='date', direction='backward')
    logger.info("시장 지표 결합 완료")
    return df


def build_features_and_labels(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 지표 계산
    df['ma5'] = df.groupby('stock_name')['close'].transform(lambda x: x.rolling(5).mean())
    df['ma20'] = df.groupby('stock_name')['close'].transform(lambda x: x.rolling(20).mean())
    df['ma60'] = df.groupby('stock_name')['close'].transform(lambda x: x.rolling(60).mean())

    # MACD
    if 'macd' not in df.columns:
        ema12 = df.groupby('stock_name')['close'].transform(lambda x: x.ewm(span=12, adjust=False).mean())
        ema26 = df.groupby('stock_name')['close'].transform(lambda x: x.ewm(span=26, adjust=False).mean())
        df['macd'] = ema12 - ema26

    db_macd = df['macd']
    db_macd_signal = df.groupby('stock_name')['macd'].transform(lambda x: x.ewm(span=9, adjust=False).mean())

    # 스토캐스틱
    low_min = df.groupby('stock_name')['low'].transform(lambda x: x.rolling(12).min())
    high_max = df.groupby('stock_name')['high'].transform(lambda x: x.rolling(12).max())
    fast_k = 100 * ((df['close'] - low_min) / (high_max - low_min))
    df['stoch_k'] = df.groupby('stock_name')['close'].transform(lambda x: fast_k.rolling(3).mean()) if False else fast_k.rolling(3).mean()
    df['stoch_d'] = df['stoch_k'].rolling(5).mean()
    df['stoch_prev_k'] = df['stoch_k'].shift(1)
    df['stoch_prev_d'] = df['stoch_d'].shift(1)

    # OBV
    direction = np.sign(df['close'].diff())
    df['obv'] = (direction * df['volume']).cumsum()

    # 시장 지표
    df['sp500_ma20'] = df['sp500'].rolling(20).mean() if 'sp500' in df.columns else 1
    df['vix_change'] = df['vix'].pct_change() if 'vix' in df.columns else 0
    df['vix_value'] = df['vix'] if 'vix' in df.columns else 20

    # 파생 피처
    df['ma5_20_ratio'] = df['ma5'] / df['ma20']
    df['ma20_60_ratio'] = df['ma20'] / df['ma60']
    df['close_ma60_ratio'] = df['close'] / df['ma60']
    df['vol_change'] = df['volume'].pct_change()
    df['macd_change'] = db_macd.diff()
    df['stoch_k_change'] = df['stoch_k'].diff()
    df['sp500_ma_ratio'] = (df['sp500'] / df['sp500_ma20']) if 'sp500' in df.columns else 1

    # 레이블링
    cond_yang = df['close'] > df['open']
    cond_eum = df['close'] < df['open']
    ma5_20_prev = df['ma5'].shift(1) / df['ma20'].shift(1)
    cond_gc = (df['ma5'] > df['ma20']) & (ma5_20_prev <= 1)
    cond_ma60 = (df['close'] >= df['ma60'])
    cond_macd_pos = db_macd > db_macd_signal
    cond_macd_up = db_macd > db_macd.shift(1)
    cond_macd = cond_macd_pos & cond_macd_up
    cond_stoch = df['stoch_k'] > df['stoch_d']
    cond_obv = df['obv'] > df['obv'].shift(1)
    cond_sp_bear = (df['sp500'] < df['sp500_ma20']) if 'sp500' in df.columns else False
    cond_vix_panic = (df['vix_change'] >= 0.10) if 'vix' in df.columns else False
    cond_ma5_up = df['ma5'] > df['ma5'].shift(1)
    cond_stoch_up = df['stoch_k'] > df['stoch_k'].shift(1)
    watch = cond_ma5_up & cond_macd & cond_stoch_up & cond_obv
    cond_stoch_ob = (df['stoch_k'] >= 80) & (df['stoch_prev_k'] < 80)
    watch_buy_ex = watch & cond_stoch_ob

    df['target'] = -1
    base_buy = cond_yang & cond_macd & cond_stoch & cond_gc & cond_ma60 & cond_obv
    buy_mask = ((base_buy.shift(1) == True) | watch_buy_ex) & (~cond_sp_bear)
    df.loc[buy_mask, 'target'] = 1

    dead_cross = (df['stoch_k'] < df['stoch_d']) & (df['stoch_prev_k'] >= df['stoch_prev_d'])
    cond_vol_up = df['volume'] > df['volume'].shift(1)
    sell_mask = (dead_cross & cond_vol_up & cond_eum) | cond_vix_panic
    df.loc[sell_mask, 'target'] = 0

    watch_mask = (df['target'] == -1) & watch
    df.loc[watch_mask, 'target'] = 2

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df = df[df['target'] != -1].copy()
    df.dropna(subset=FEATURE_COLS + ['target'], inplace=True)
    return df


def train_and_save():
    raw = load_csv_data()
    raw = add_market_data(raw)
    dataset = build_features_and_labels(raw)

    X = dataset[FEATURE_COLS]
    y = dataset['target']
    logger.info(f"학습 데이터: {len(X)}행, 클래스 분포: {y.value_counts().to_dict()}")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    sample_weights = compute_sample_weight(class_weight='balanced', y=y_train)

    model = XGBClassifier(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=4,
        random_state=42,
        eval_metric='mlogloss',
    )
    model.fit(X_train, y_train, sample_weight=sample_weights,
              eval_set=[(X_test, y_test)], verbose=False)

    from sklearn.metrics import accuracy_score
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    logger.info(f"검증 정확도: {acc:.4f}")

    model.save_model(MODEL_PATH)
    logger.info(f"모델 저장 완료: {MODEL_PATH}")
    return model


if __name__ == '__main__':
    train_and_save()
