"""
드리프트 감지 모듈
- PSI (Population Stability Index) 기반 데이터 드리프트 감지
- 수익률 기반 성능 드리프트 감지 (실전 성능)
- 둘 다 감지될 때만 재학습 트리거
"""
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
import logging

logger = logging.getLogger(__name__)

# PSI 임계값: 0.1 이하 = 안정, 0.1~0.25 = 주의, 0.25 이상 = 드리프트
PSI_THRESHOLD = 0.25

# 수익률 드리프트 임계값
# 최근 1주일 모의 수익률이 이 값 이하면 드리프트로 판단
RETURN_DROP_THRESHOLD = -0.03   # -3% 이하면 드리프트


def calculate_psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    """
    PSI (Population Stability Index) 계산
    expected: 학습 시점 데이터 분포
    actual: 현재 데이터 분포
    반환값: PSI 수치 (0.25 이상이면 드리프트)
    """
    def psi_bucket(expected_arr, actual_arr, bucket_min, bucket_max):
        expected_ratio = np.sum((expected_arr >= bucket_min) & (expected_arr < bucket_max)) / len(expected_arr)
        actual_ratio = np.sum((actual_arr >= bucket_min) & (actual_arr < bucket_max)) / len(actual_arr)
        expected_ratio = max(expected_ratio, 1e-6)
        actual_ratio = max(actual_ratio, 1e-6)
        return (actual_ratio - expected_ratio) * np.log(actual_ratio / expected_ratio)

    breakpoints = np.linspace(
        min(expected.min(), actual.min()),
        max(expected.max(), actual.max()),
        buckets + 1
    )

    psi = sum(
        psi_bucket(expected, actual, breakpoints[i], breakpoints[i + 1])
        for i in range(buckets)
    )
    return psi


def detect_data_drift(
    train_df: pd.DataFrame,
    new_df: pd.DataFrame,
    feature_cols: list
) -> dict:
    """
    피처별 PSI 계산으로 데이터 드리프트 감지
    """
    results = {}
    drifted_features = []

    for col in feature_cols:
        if col not in train_df.columns or col not in new_df.columns:
            continue

        train_vals = train_df[col].dropna().values
        new_vals = new_df[col].dropna().values

        if len(train_vals) == 0 or len(new_vals) == 0:
            continue

        psi = calculate_psi(train_vals, new_vals)
        results[col] = round(psi, 4)

        if psi >= PSI_THRESHOLD:
            drifted_features.append(col)
            logger.warning(f"PSI 드리프트 감지: {col} PSI={psi:.4f} (임계값 {PSI_THRESHOLD})")

    results['drifted_features'] = drifted_features
    results['drift_detected'] = len(drifted_features) > 0
    results['max_psi'] = max((v for v in results.values() if isinstance(v, float)), default=0.0)

    return results


def detect_return_drift(
    model,
    recent_df: pd.DataFrame,
    feature_cols: list,
    hold_days: int = 5
) -> dict:
    """
    최근 N일 데이터에 모델을 적용해서 모의 수익률 계산
    수익률이 임계값 이하면 드리프트로 판단

    recent_df: 최근 데이터 (date, close, feature_cols 포함)
    hold_days: 매수 후 보유 일수
    """
    df = recent_df.copy().reset_index(drop=True)
    X = df[feature_cols].dropna()

    if len(X) < hold_days + 1:
        logger.warning("수익률 계산을 위한 데이터 부족")
        return {'drift_detected': False, 'weekly_return': None, 'reason': '데이터 부족'}

    df = df.loc[X.index].copy()
    df['predicted'] = model.predict(X)

    # 매수 신호(1) 발생일의 hold_days 후 수익률 계산
    returns = []
    for i in range(len(df) - hold_days):
        if df.iloc[i]['predicted'] == 1:  # 매수 신호
            buy_price = df.iloc[i]['close']
            sell_price = df.iloc[i + hold_days]['close']
            ret = (sell_price - buy_price) / buy_price
            returns.append(ret)

    if len(returns) == 0:
        logger.info("매수 신호 없음. 수익률 드리프트 판단 불가.")
        return {'drift_detected': False, 'weekly_return': None, 'reason': '매수 신호 없음'}

    avg_return = float(np.mean(returns))
    drift_detected = avg_return < RETURN_DROP_THRESHOLD

    if drift_detected:
        logger.warning(
            f"수익률 드리프트 감지: 평균 수익률={avg_return:.4f} "
            f"(임계값 {RETURN_DROP_THRESHOLD}), 매수 신호 수={len(returns)}"
        )
    else:
        logger.info(f"수익률 정상: 평균 수익률={avg_return:.4f}, 매수 신호 수={len(returns)}")

    return {
        'drift_detected': drift_detected,
        'avg_return': round(avg_return, 4),
        'signal_count': len(returns),
        'threshold': RETURN_DROP_THRESHOLD
    }


def check_drift(
    model,
    train_df: pd.DataFrame,
    recent_df: pd.DataFrame,
    feature_cols: list,
    hold_days: int = 5
) -> dict:
    """
    PSI 드리프트 + 수익률 드리프트 통합 체크
    둘 다 감지될 때만 재학습 트리거
    """
    logger.info("=" * 40)
    logger.info("드리프트 감지 시작")
    logger.info("=" * 40)

    # 1. PSI 데이터 드리프트 체크
    data_drift = detect_data_drift(train_df, recent_df, feature_cols)
    psi_drift = data_drift.get('drift_detected', False)
    logger.info(f"PSI 드리프트: {'감지' if psi_drift else '정상'} (max PSI={data_drift.get('max_psi', 0):.4f})")

    # 2. 수익률 드리프트 체크
    return_drift = detect_return_drift(model, recent_df, feature_cols, hold_days)
    ret_drift = return_drift.get('drift_detected', False)
    logger.info(f"수익률 드리프트: {'감지' if ret_drift else '정상'} (avg_return={return_drift.get('avg_return', 'N/A')})")

    # 3. 둘 다 감지될 때만 재학습
    retrain_needed = psi_drift and ret_drift

    if retrain_needed:
        logger.warning("PSI + 수익률 드리프트 둘 다 감지 → 재학습 트리거")
    elif psi_drift:
        logger.info("PSI 드리프트만 감지 → 수익률은 정상이므로 재학습 보류")
    elif ret_drift:
        logger.info("수익률 드리프트만 감지 → PSI는 정상이므로 재학습 보류")
    else:
        logger.info("드리프트 없음 → 재학습 불필요")

    return {
        'data_drift': data_drift,
        'return_drift': return_drift,
        'psi_drift': psi_drift,
        'ret_drift': ret_drift,
        'retrain_needed': retrain_needed
    }
