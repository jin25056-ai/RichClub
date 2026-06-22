"""
재학습 파이프라인
- 매주 월요일 오전 8시 스케줄러에서 호출
- PSI 드리프트 + 수익률 드리프트 둘 다 감지될 때만 재학습
- 신규 데이터 포함해서 전체 재학습
- 재학습 후 예측 결과 자동으로 MongoDB 업로드
"""
import os
import json
import joblib
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.metrics import accuracy_score, classification_report
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier
import yfinance as yf

try:
    from app.ml.drift_detector import check_drift
except ImportError:
    from drift_detector import check_drift

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
MODEL_PATH = os.path.join(MODEL_DIR, 'xgb_model.pkl')
METADATA_PATH = os.path.join(MODEL_DIR, 'model_metadata.json')
TRAIN_DATA_PATH = os.path.join(MODEL_DIR, 'train_reference.pkl')

FEATURE_COLS = [
    'ma5_20_ratio', 'ma20_60_ratio', 'close_ma60_ratio',
    'vol_change', 'macd', 'stoch_k', 'stoch_d', 'obv',
    'macd_change', 'stoch_k_change', 'sp500_ma_ratio', 'vix_value'
]

SIGNAL_MAP = {0: "매도", 1: "매수", 2: "관망"}


def _get_mongo_db():
    load_dotenv()
    client = MongoClient(os.getenv("MONGO_URI"))
    db_name = os.getenv("MONGODB_DB", os.getenv("DB_NAME", "richclub"))
    return client[db_name]


def load_data_from_mongo() -> pd.DataFrame:
    db = _get_mongo_db()
    collection = db[os.getenv("COLLECTION_NAME")]
    raw_df = pd.DataFrame(list(collection.find()))
    if '_id' in raw_df.columns:
        raw_df.drop(columns=['_id'], inplace=True)
    raw_df.columns = [col.lower() for col in raw_df.columns]
    if 'date' in raw_df.columns:
        raw_df['date'] = pd.to_datetime(raw_df['date'])
        raw_df.sort_values('date', ascending=True, inplace=True)
        raw_df.reset_index(drop=True, inplace=True)
    return raw_df


def fetch_market_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    start_date = raw_df['date'].min().strftime('%Y-%m-%d')
    end_date = (raw_df['date'].max() + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    logger.info(f"yfinance 시장 지표 수집 중... ({start_date} ~ {end_date})")
    market_data = yf.download(["^GSPC", "^VIX"], start=start_date, end=end_date, interval="1d")
    market_df = pd.DataFrame(index=market_data.index)
    market_df['sp500'] = market_data[('Close', '^GSPC')]
    market_df['vix'] = market_data[('Close', '^VIX')]
    market_df.reset_index(inplace=True)
    market_df.rename(columns={'Date': 'date'}, inplace=True)
    market_df['date'] = pd.to_datetime(market_df['date'])
    return pd.merge_asof(raw_df, market_df, on='date', direction='backward')


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma60'] = df['close'].rolling(window=60).mean()
    db_macd = df['macd']
    db_macd_signal = db_macd.ewm(span=9, adjust=False).mean()
    low_min = df['low'].rolling(window=12).min()
    high_max = df['high'].rolling(window=12).max()
    fast_k = 100 * ((df['close'] - low_min) / (high_max - low_min))
    df['stoch_k'] = fast_k.rolling(window=3).mean()
    df['stoch_d'] = df['stoch_k'].rolling(window=5).mean()
    df['stoch_prev_k'] = df['stoch_k'].shift(1)
    df['stoch_prev_d'] = df['stoch_d'].shift(1)
    direction = np.sign(df['close'].diff())
    direction.iloc[0] = 0
    df['obv'] = (direction * df['volume']).cumsum()
    df['sp500_ma20'] = df['sp500'].rolling(window=20).mean()
    df['vix_change'] = df['vix'].pct_change()
    df['ma5_20_ratio'] = df['ma5'] / df['ma20']
    df['ma20_60_ratio'] = df['ma20'] / df['ma60']
    df['close_ma60_ratio'] = df['close'] / df['ma60']
    df['vol_change'] = df['volume'].pct_change()
    df['macd_change'] = db_macd.diff()
    df['stoch_k_change'] = df['stoch_k'].diff()
    df['sp500_ma_ratio'] = df['sp500'] / df['sp500_ma20']
    df['vix_value'] = df['vix']

    cond_yang_bong = df['close'] > df['open']
    cond_eum_bong = df['close'] < df['open']
    ma5_20_prev_ratio = df['ma5'].shift(1) / df['ma20'].shift(1)
    cond_ma5_20_gc = (df['ma5'] > df['ma20']) & (ma5_20_prev_ratio <= 1)
    cond_ma60_above = df['close'] >= df['ma60']
    close_ma60_prev_ratio = df['close'].shift(1) / df['ma60'].shift(1)
    cond_ma60_gc = (df['close'] >= df['ma60']) & (close_ma60_prev_ratio < 1)
    cond_ma60_filter = cond_ma60_above | cond_ma60_gc
    cond_macd_pure = db_macd > db_macd_signal
    cond_macd_rising = db_macd > db_macd.shift(1)
    cond_macd_total = cond_macd_pure & cond_macd_rising
    cond_stoch_pure = df['stoch_k'] > df['stoch_d']
    cond_obv_rising = df['obv'] > df['obv'].shift(1)
    cond_ma5_rising = df['ma5'] > df['ma5'].shift(1)
    cond_stoch_k_rising = df['stoch_k'] > df['stoch_k'].shift(1)
    watch_signal = cond_ma5_rising & cond_macd_total & cond_stoch_k_rising & cond_obv_rising
    cond_stoch_overbought_enter = (df['stoch_k'] >= 80) & (df['stoch_prev_k'] < 80)
    watch_buy_exception = watch_signal & cond_stoch_overbought_enter
    cond_sp500_bear_market = df['sp500'] < df['sp500_ma20']
    cond_vix_panic = df['vix_change'] >= 0.10

    df['target'] = -1
    base_buy_signal = (
        cond_yang_bong & cond_macd_total & cond_stoch_pure &
        cond_ma5_20_gc & cond_ma60_filter & cond_obv_rising
    )
    buy_mask = ((base_buy_signal.shift(1) == True) | watch_buy_exception) & (~cond_sp500_bear_market)
    df.loc[buy_mask, 'target'] = 1

    is_stoch_dead_cross = (df['stoch_k'] < df['stoch_d']) & (df['stoch_prev_k'] >= df['stoch_prev_d'])
    cond_vol_rising = df['volume'] > df['volume'].shift(1)
    sell_mask = (is_stoch_dead_cross & cond_vol_rising & cond_eum_bong) | cond_vix_panic
    df.loc[sell_mask, 'target'] = 0

    watch_mask = (df['target'] == -1) & watch_signal
    df.loc[watch_mask, 'target'] = 2

    df['_cond_yang_bong'] = cond_yang_bong
    df['_cond_ma5_20_gc'] = cond_ma5_20_gc
    df['_cond_ma60_filter'] = cond_ma60_filter
    df['_cond_macd_total'] = cond_macd_total
    df['_cond_stoch_pure'] = cond_stoch_pure
    df['_cond_obv_rising'] = cond_obv_rising
    df['_cond_not_bear'] = ~cond_sp500_bear_market

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df = df[df['target'] != -1].copy()
    df.dropna(subset=['target'] + FEATURE_COLS, inplace=True)
    return df


def train_model(dataset: pd.DataFrame) -> tuple:
    split_idx = int(len(dataset) * 0.8)
    train_df = dataset.iloc[:split_idx]
    test_df = dataset.iloc[split_idx:]
    X_train = train_df[FEATURE_COLS]
    y_train = train_df['target']
    X_test = test_df[FEATURE_COLS]
    y_test = test_df['target']
    sample_weights = compute_sample_weight(class_weight='balanced', y=y_train)
    model = XGBClassifier(
        n_estimators=200, learning_rate=0.05, max_depth=4,
        random_state=42, eval_metric='mlogloss'
    )
    model.fit(X_train, y_train, sample_weight=sample_weights,
              eval_set=[(X_test, y_test)], verbose=False)
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    logger.info(f"모델 학습 완료. 정확도: {accuracy:.4f}")
    logger.info(f"\n{classification_report(y_test, y_pred, target_names=['매도(0)', '매수(1)', '관망(2)'], labels=[0, 1, 2])}")
    return model, accuracy, train_df


def save_model(model, accuracy: float, train_df: pd.DataFrame):
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    joblib.dump(train_df, TRAIN_DATA_PATH)
    metadata = {
        'trained_at': datetime.now().isoformat(),
        'accuracy': accuracy,
        'feature_cols': FEATURE_COLS,
        'train_data_rows': len(train_df)
    }
    with open(METADATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    logger.info(f"모델 저장 완료: {MODEL_PATH}")


def load_model():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"모델 파일이 없습니다: {MODEL_PATH}")
    model = joblib.load(MODEL_PATH)
    with open(METADATA_PATH, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    train_df = joblib.load(TRAIN_DATA_PATH)
    logger.info(f"모델 로드 완료. 학습 시점: {metadata['trained_at']}, 정확도: {metadata['accuracy']:.4f}")
    return model, metadata, train_df


def _export_predictions_and_upload(model, dataset: pd.DataFrame):
    X = dataset[FEATURE_COLS]
    proba = model.predict_proba(X)
    preds = model.predict(X)

    COND_LABELS = {
        '_cond_yang_bong': '양봉 (종가 > 시가)',
        '_cond_ma5_20_gc': '5/20일선 골든크로스',
        '_cond_ma60_filter': '60일선 위 또는 상향 돌파',
        '_cond_macd_total': 'MACD 정배열 및 상승',
        '_cond_stoch_pure': '스토캐스틱 K > D',
        '_cond_obv_rising': 'OBV 상승 (거래량 수반)',
        '_cond_not_bear': 'S&P500 하락장 아님',
    }

    importances = model.feature_importances_
    fi_list = [
        {"feature": col, "importance": round(float(imp), 4)}
        for col, imp in sorted(zip(FEATURE_COLS, importances), key=lambda x: -x[1])
    ]

    docs = []
    now = datetime.now(timezone.utc)
    for i, (idx, row) in enumerate(dataset.iterrows()):
        pred_label = int(preds[i])
        confidence = round(float(proba[i][pred_label]), 4)
        conditions_met, conditions_not_met = [], []
        for col, label in COND_LABELS.items():
            if col in dataset.columns:
                (conditions_met if bool(dataset.at[idx, col]) else conditions_not_met).append(label)

        docs.append({
            'stock_code': str(row.get('stock_code', row.get('stock_name', ''))),
            'stock_name': str(row.get('stock_name', '')),
            'close': _sf(row.get('close')), 'open': _sf(row.get('open')),
            'high': _sf(row.get('high')), 'low': _sf(row.get('low')),
            'volume': _sf(row.get('volume')),
            'signal': SIGNAL_MAP[pred_label], 'signal_label': pred_label,
            'confidence': confidence,
            'rsi': _sf(row.get('rsi')), 'macd': _sf(row.get('macd')),
            'stoch_k': _sf(row.get('stoch_k')), 'stoch_d': _sf(row.get('stoch_d')),
            'obv': _sf(row.get('obv')),
            'ma5_20_ratio': _sf(row.get('ma5_20_ratio')),
            'ma20_60_ratio': _sf(row.get('ma20_60_ratio')),
            'close_ma60_ratio': _sf(row.get('close_ma60_ratio')),
            'macd_change': _sf(row.get('macd_change')),
            'stoch_k_change': _sf(row.get('stoch_k_change')),
            'sp500_ma_ratio': _sf(row.get('sp500_ma_ratio')),
            'vix_value': _sf(row.get('vix_value')),
            'sp500': _sf(row.get('sp500')), 'vix': _sf(row.get('vix')),
            'conditions_met': conditions_met,
            'conditions_not_met': conditions_not_met,
            'feature_importance': fi_list,
            'predicted_at': _parse_date(row.get('date')),
            'uploaded_at': now,
        })

    db = _get_mongo_db()
    col = db['total_trading_signals']
    col.drop()
    if docs:
        col.insert_many(docs)
    col.create_index([("stock_code", 1), ("predicted_at", -1)])
    col.create_index([("signal", 1)])
    col.create_index([("predicted_at", -1)])
    logger.info(f"MongoDB total_trading_signals 업로드 완료: {len(docs)}건")


def _sf(val):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return float(val)
    except Exception:
        return None


def _parse_date(val) -> datetime:
    try:
        return pd.to_datetime(val).to_pydatetime().replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def run_drift_check_and_retrain():
    logger.info("=" * 50)
    logger.info("드리프트 감지 파이프라인 시작")
    logger.info("=" * 50)

    raw_df = load_data_from_mongo()
    raw_df = fetch_market_data(raw_df)
    new_dataset = build_features(raw_df)

    if len(new_dataset) < 10:
        logger.warning("데이터 부족. 드리프트 감지 생략.")
        return

    if not os.path.exists(MODEL_PATH):
        logger.info("저장된 모델이 없습니다. 최초 학습 실행.")
        model, accuracy, train_df = train_model(new_dataset)
        save_model(model, accuracy, train_df)
        _export_predictions_and_upload(model, new_dataset)
        return

    model, metadata, train_df = load_model()

    cutoff = new_dataset['date'].max() - pd.Timedelta(days=7)
    recent_df = new_dataset[new_dataset['date'] >= cutoff]

    if len(recent_df) < 5:
        logger.warning(f"최근 7일 데이터 부족 ({len(recent_df)}건). 드리프트 감지 생략.")
        return

    drift_result = check_drift(
        model=model, train_df=train_df, recent_df=recent_df,
        feature_cols=FEATURE_COLS, hold_days=5
    )

    logger.info(f"드리프트 감지 결과: retrain_needed={drift_result['retrain_needed']}")

    if drift_result['retrain_needed']:
        logger.info("재학습 시작...")
        model, accuracy, train_df = train_model(new_dataset)
        save_model(model, accuracy, train_df)
        _export_predictions_and_upload(model, new_dataset)
    else:
        logger.info("재학습 조건 미충족. 재학습 생략.")

    logger.info("드리프트 감지 파이프라인 종료")
    return drift_result


if __name__ == '__main__':
    run_drift_check_and_retrain()
