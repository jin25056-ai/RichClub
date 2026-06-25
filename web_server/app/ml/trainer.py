"""
app/ml/trainer.py

XGBoost 모델 학습 및 저장
- yfinance로 전 종목 OHLCV 수집
- 피처 계산 + 레이블링 (train_model_xgb_v5.py 로직 동일)
- 학습 후 모델 저장 + 메타데이터 DB 기록

모델 파일 위치: /app/models/xgb_model.json
"""
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.metrics import accuracy_score, classification_report
from xgboost import XGBClassifier
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "/app/models")
MODEL_PATH = os.path.join(MODEL_DIR, "xgb_model.json")

FEATURE_COLS = [
    'ma5_20_ratio', 'ma20_60_ratio', 'close_ma60_ratio',
    'vol_change', 'macd', 'stoch_k', 'stoch_d', 'obv',
    'macd_change', 'stoch_k_change', 'sp500_ma_ratio', 'vix_value'
]
LABEL_MAP = {0: '매도', 1: '매수', 2: '관망'}

# KOSPI 주요 종목 (kospi_list.xlsx 대신 하드코딩 - 서버에서 독립 실행)
KOSPI_STOCKS = [
    ("005930.KS", "삼성전자", "005930"),
    ("000660.KS", "SK하이닉스", "000660"),
    ("005935.KS", "삼성전자우", "005935"),
    ("373220.KS", "LG에너지솔루션", "373220"),
    ("207940.KS", "삼성바이오로직스", "207940"),
    ("005380.KS", "현대차", "005380"),
    ("000270.KS", "기아", "000270"),
    ("068270.KS", "셀트리온", "068270"),
    ("051910.KS", "LG화학", "051910"),
    ("035420.KS", "NAVER", "035420"),
    ("028260.KS", "삼성물산", "028260"),
    ("012330.KS", "현대모비스", "012330"),
    ("066570.KS", "LG전자", "066570"),
    ("003550.KS", "LG", "003550"),
    ("032830.KS", "삼성생명", "032830"),
    ("086790.KS", "하나금융지주", "086790"),
    ("105560.KS", "KB금융", "105560"),
    ("055550.KS", "신한지주", "055550"),
    ("096770.KS", "SK이노베이션", "096770"),
    ("017670.KS", "SK텔레콤", "017670"),
    ("034730.KS", "SK", "034730"),
    ("042660.KS", "한화오션", "042660"),
    ("329180.KS", "HD현대중공업", "329180"),
    ("009830.KS", "한화솔루션", "009830"),
    ("402340.KS", "SK스퀘어", "402340"),
    ("047810.KS", "한국항공우주", "047810"),
    ("003670.KS", "포스코퓨처엠", "003670"),
    ("010130.KS", "고려아연", "010130"),
    ("035720.KS", "카카오", "035720"),
    ("251270.KS", "넷마블", "251270"),
    ("036570.KS", "NC", "036570"),
    ("259960.KS", "크래프톤", "259960"),
    ("352820.KS", "하이브", "352820"),
    ("000100.KS", "유한양행", "000100"),
    ("128940.KS", "한미약품", "128940"),
    ("068760.KS", "셀트리온제약", "068760"),
    ("090430.KS", "아모레퍼시픽", "090430"),
    ("011200.KS", "HMM", "011200"),
    ("028670.KS", "팬오션", "028670"),
    ("006400.KS", "삼성SDI", "006400"),
    ("010950.KS", "S-Oil", "010950"),
    ("011790.KS", "SKC", "011790"),
    ("298040.KS", "효성중공업", "298040"),
    ("010120.KS", "LS ELECTRIC", "010120"),
    ("004020.KS", "현대제철", "004020"),
    ("139480.KS", "이마트", "139480"),
    ("069960.KS", "현대백화점", "069960"),
    ("004990.KS", "롯데지주", "004990"),
    ("023530.KS", "롯데쇼핑", "023530"),
    ("282330.KS", "BGF리테일", "282330"),
]


def _fetch_market_data(start: str, end: str) -> dict:
    try:
        mkt = yf.download(["^GSPC", "^VIX"], start=start, end=end, interval="1d", progress=False)
        if mkt.empty:
            return {}
        if isinstance(mkt.columns, pd.MultiIndex):
            # yfinance 1.4+: ('Close', '^GSPC') 형태
            sp500 = mkt['Close']['^GSPC'] if '^GSPC' in mkt['Close'].columns else mkt['Close'].iloc[:, 0]
            vix = mkt['Close']['^VIX'] if '^VIX' in mkt['Close'].columns else mkt['Close'].iloc[:, 1]
        else:
            sp500 = mkt['Close']
            vix = mkt['Close']
        return {
            pd.Timestamp(k).strftime('%Y-%m-%d'): {
                'sp500': float(sp500.get(k, np.nan)),
                'vix': float(vix.get(k, np.nan)),
            }
            for k in sp500.index
        }
    except Exception as e:
        logger.warning(f"시장 데이터 수집 실패: {e}")
        return {}


def _build_features(raw: pd.DataFrame, market_map: dict, stock_name: str) -> pd.DataFrame:
    df = raw.copy()
    # yfinance 1.4+ MultiIndex 처리: ('Close', 'TICKER') -> 'Close'
    if isinstance(df.columns, pd.MultiIndex):
        # 단일 종목이면 ticker 레벨 제거
        if df.columns.nlevels == 2:
            df.columns = df.columns.get_level_values(0)
        else:
            df.columns = df.columns.droplevel(-1)
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={'adj close': 'close', 'price': 'close'})
    df.index = pd.to_datetime(df.index)
    df = df.dropna(subset=['close'])
    df['stock_name'] = stock_name

    close = df['close']
    df['ma5'] = close.rolling(5).mean()
    df['ma20'] = close.rolling(20).mean()
    df['ma60'] = close.rolling(60).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    low_min = df['low'].rolling(12).min()
    high_max = df['high'].rolling(12).max()
    fast_k = 100 * ((close - low_min) / (high_max - low_min).replace(0, np.nan))
    df['stoch_k'] = fast_k.rolling(3).mean()
    df['stoch_d'] = df['stoch_k'].rolling(5).mean()
    df['stoch_prev_k'] = df['stoch_k'].shift(1)
    df['stoch_prev_d'] = df['stoch_d'].shift(1)
    direction = np.sign(close.diff())
    df['obv'] = (direction * df['volume']).fillna(0).cumsum()

    sp500_s = pd.Series({pd.Timestamp(k): v['sp500'] for k, v in market_map.items()})
    vix_s = pd.Series({pd.Timestamp(k): v['vix'] for k, v in market_map.items()})
    df['sp500'] = sp500_s.reindex(df.index, method='ffill')
    df['vix'] = vix_s.reindex(df.index, method='ffill')
    df['sp500_ma20'] = df['sp500'].rolling(20).mean()
    df['vix_change'] = df['vix'].pct_change()
    df['vix_value'] = df['vix']

    df['ma5_20_ratio'] = df['ma5'] / df['ma20']
    df['ma20_60_ratio'] = df['ma20'] / df['ma60']
    df['close_ma60_ratio'] = close / df['ma60']
    df['vol_change'] = df['volume'].pct_change()
    df['macd_change'] = df['macd'].diff()
    df['stoch_k_change'] = df['stoch_k'].diff()
    df['sp500_ma_ratio'] = df['sp500'] / df['sp500_ma20']

    # 레이블링 (train_model_xgb_v5.py 동일)
    cond_yang = close > df['open']
    cond_eum = close < df['open']
    ma5_20_prev = df['ma5'].shift(1) / df['ma20'].shift(1)
    cond_gc = (df['ma5'] > df['ma20']) & (ma5_20_prev <= 1)
    cond_ma60 = close >= df['ma60']
    macd_sig = df['macd'].ewm(span=9, adjust=False).mean()
    cond_macd = (df['macd'] > macd_sig) & (df['macd'] > df['macd'].shift(1))
    cond_stoch = df['stoch_k'] > df['stoch_d']
    cond_obv = df['obv'] > df['obv'].shift(1)
    cond_sp_bear = df['sp500'] < df['sp500_ma20']
    cond_vix_panic = df['vix_change'] >= 0.10
    cond_ma5_up = df['ma5'] > df['ma5'].shift(1)
    cond_stoch_up = df['stoch_k'] > df['stoch_k'].shift(1)
    watch = cond_ma5_up & cond_macd & cond_stoch_up & cond_obv
    watch_buy_ex = watch & ((df['stoch_k'] >= 80) & (df['stoch_prev_k'] < 80))

    df['target'] = -1
    base_buy = cond_yang & cond_macd & cond_stoch & cond_gc & cond_ma60 & cond_obv
    buy_mask = ((base_buy.shift(1) == True) | watch_buy_ex) & (~cond_sp_bear)
    df.loc[buy_mask, 'target'] = 1
    dead_cross = (df['stoch_k'] < df['stoch_d']) & (df['stoch_prev_k'] >= df['stoch_prev_d'])
    sell_mask = (dead_cross & (df['volume'] > df['volume'].shift(1)) & cond_eum) | cond_vix_panic
    df.loc[sell_mask, 'target'] = 0
    df.loc[(df['target'] == -1) & watch, 'target'] = 2

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df = df[df['target'] != -1].copy()
    df.dropna(subset=FEATURE_COLS + ['target'], inplace=True)
    return df


async def train_model(db: AsyncIOMotorDatabase, triggered_by: str = "manual") -> dict:
    """전 종목 데이터로 XGBoost 모델 학습 후 저장"""
    os.makedirs(MODEL_DIR, exist_ok=True)
    start_time = datetime.now(timezone.utc)
    logger.info(f"[trainer] 모델 학습 시작 (by={triggered_by})")

    # 2년치 데이터 수집
    end_dt = datetime.now()
    start_dt = (end_dt - timedelta(days=730)).strftime('%Y-%m-%d')
    end_str = (end_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    market_map = _fetch_market_data(start_dt, end_str)

    import asyncio
    all_dfs = []
    for ticker, name, code in KOSPI_STOCKS:
        try:
            raw = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda t=ticker: yf.download(t, start=start_dt, end=end_str,
                                              interval='1d', progress=False, auto_adjust=True)
            )
            if raw.empty or len(raw) < 100:
                continue
            df = _build_features(raw, market_map, name)
            if len(df) > 10:
                all_dfs.append(df)
        except Exception as e:
            logger.warning(f"{name} 데이터 수집 실패: {e}")

    if not all_dfs:
        raise RuntimeError("학습 데이터 없음")

    dataset = pd.concat(all_dfs, ignore_index=True)
    X = dataset[FEATURE_COLS]
    y = dataset['target']
    logger.info(f"학습 데이터: {len(X)}행, 분포: {y.value_counts().to_dict()}")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    sample_weights = compute_sample_weight(class_weight='balanced', y=y_train)

    model = XGBClassifier(
        n_estimators=200, learning_rate=0.05, max_depth=4,
        random_state=42, eval_metric='mlogloss'
    )
    model.fit(X_train, y_train, sample_weight=sample_weights,
              eval_set=[(X_test, y_test)], verbose=False)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, target_names=['매도', '매수', '관망'],
                                   labels=[0, 1, 2], output_dict=True)

    model.save_model(MODEL_PATH)
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(f"[trainer] 모델 저장 완료: {MODEL_PATH}, 정확도={acc:.4f}, 소요={elapsed:.1f}s")

    # 학습 이력 DB 저장
    meta = {
        'trained_at': start_time,
        'triggered_by': triggered_by,
        'accuracy': round(float(acc), 4),
        'n_train': int(len(X_train)),
        'n_test': int(len(X_test)),
        'elapsed_sec': round(elapsed, 1),
        'class_report': report,
        'model_path': MODEL_PATH,
        'label_dist': {str(k): int(v) for k, v in y.value_counts().items()},
        'stocks_used': len(all_dfs),
    }
    await db.model_train_history.insert_one(meta)

    return {'accuracy': round(float(acc), 4), 'n_samples': int(len(X)), 'elapsed_sec': round(elapsed, 1)}


def load_model() -> Optional[XGBClassifier]:
    """저장된 모델 로드"""
    if not os.path.exists(MODEL_PATH):
        return None
    model = XGBClassifier()
    model.load_model(MODEL_PATH)
    return model
