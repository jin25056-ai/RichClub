import os
import glob
import pandas as pd
import numpy as np
import joblib
import matplotlib.pyplot as plt
import seaborn as sns
from lightgbm import LGBMClassifier, LGBMRegressor
from xgboost import XGBClassifier, XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_squared_error, r2_score, confusion_matrix, f1_score

if __name__ == '__main__':
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RAW_DIR = r"C:\Users\human3_04\Desktop\richclub\combotest\rawdata"
    MODEL_DIR = r"C:\Users\human3_04\Desktop\richclub\combotest\train_pklFile"
    RESULT_DIR = r"C:\Users\human3_04\Desktop\richclub\combotest\test_result"
    
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    # 1. 데이터 로드
    train_years = [2021, 2022, 2023, 2024, 2025]
    all_dfs = []
    
    print("▶ [1/7] 학습 데이터 로드 시작...")
    for year in train_years:
        file_path = os.path.join(RAW_DIR, f'engineered_stock_data_{year}.csv')
        if os.path.exists(file_path):
            df_year = pd.read_csv(file_path, encoding='utf-8-sig')
            if len(df_year) > 0:
                all_dfs.append(df_year)
                print(f"   - {year}년 데이터 로드 완료 ({len(df_year)}건)")
            
    if not all_dfs:
        raise FileNotFoundError("학습할 데이터 파일이 존재하지 않습니다.")
        
    df_total = pd.concat(all_dfs, ignore_index=True)
    print(f"▶ 총 합산 데이터 건수: {len(df_total)}건")
    
    # ⚡ [교정] 타겟 대상에서 final_target 및 관련 컬럼들을 피처에서 제외
    exclude_cols = ['stk_cd', 'date', 'year', 'ticker', 'target', 'final_target', 
                    'target_5pct_nextday', 'target_15pct_5d', 'target_30pct_10d']
    
    # 지표(Feature) 컬럼 정의
    feature_cols = [c for c in df_total.columns if c not in exclude_cols]
    
    # 데이터 정형화
    for col in feature_cols:
        df_total[col] = pd.to_numeric(df_total[col], errors='coerce')
    df_total[feature_cols] = df_total[feature_cols].fillna(0)
    
    X = df_total[feature_cols]

    # ⚡ 학습에 사용된 피처 목록과 순서를 명시적으로 저장합니다.
    joblib.dump(feature_cols, os.path.join(MODEL_DIR, "model_features.pkl"))
    print(f"▶ [교정] 학습 피처 목록 저장 완료 (총 {len(feature_cols)}개 피처)")
    
    # ⚡ [핵심 수정] 꼬여있던 'target' 대신 엔지니어링된 'final_target'을 진짜 타겟으로 지정!
    if 'target' not in df_total.columns:
        raise KeyError("데이터셋에 'target' 컬럼이 존재하지 않습니다. 전처리 파일 생성을 다시 확인해주세요.")
        
    raw_targets = df_total['target'].fillna(0).astype(int).values
    unique_targets = np.unique(raw_targets)
    
    print(f"▶ Detected Real Labels in target: {unique_targets}")
    
    # XGBoost 다중분류 에러 방지용 순차 인덱스 맵핑
    label_to_idx = {val: idx for idx, val in enumerate(unique_targets)}
    idx_to_label = {idx: val for idx, val in enumerate(unique_targets)}
    
    y_clf = np.array([label_to_idx[y] for y in raw_targets])
    y_reg = df_total['reg_return_5d'].fillna(0) if 'reg_return_5d' in df_total.columns else df_total['pred_rt'].fillna(0)
    
    joblib.dump({'label_to_idx': label_to_idx, 'idx_to_label': idx_to_label}, 
                os.path.join(MODEL_DIR, "target_label_map.pkl"))
    
    # 데이터 분할
    X_train, X_val, y_train_clf, y_val_clf = train_test_split(X, y_clf, test_size=0.2, random_state=42)
    _, _, y_train_reg, y_val_reg = train_test_split(X, y_reg, test_size=0.2, random_state=42)
    
    # 시각화 라벨 이름 동적 매핑
    label_names_dict = {0: '매도(0)', 1: '급등/매수(1)', 2: '관망(2)', 3: '침체(3)'}
    class_names = [label_names_dict.get(idx_to_label[i], f"Class {idx_to_label[i]}") for i in range(len(unique_targets))]
    
    results = {}
    
    # 폰트 설정
    plt.rc('font', family='Malgun Gothic')
    plt.rcParams['axes.unicode_minus'] = False
    
    # 2x3 그리드 설정
    fig_clf, axes_clf = plt.subplots(2, 3, figsize=(26, 16))
    
    # 클래스 가중치 자동 계산
    class_counts = np.bincount(y_train_clf, minlength=len(unique_targets))
    total_samples = len(y_train_clf)
    class_weights = {i: total_samples / (len(unique_targets) * count) if count > 0 else 1.0 for i, count in enumerate(class_counts)}
    sample_weights_train = np.array([class_weights[y] for y in y_train_clf])

    # ==========================================
    # 3. Model 1: LightGBM Classifier
    # ==========================================
    print("\n▶ [2/7] 학습 진행중... LightGBM Classifier")
    lgb_clf = LGBMClassifier(n_estimators=300, learning_rate=0.05, max_depth=6, 
                             class_weight='balanced', random_state=42, verbose=-1)
    lgb_clf.fit(X_train, y_train_clf)
    preds_lgb_clf = lgb_clf.predict(X_val)
    
    acc_lgb_clf = accuracy_score(y_val_clf, preds_lgb_clf)
    f1_lgb_clf = f1_score(y_val_clf, preds_lgb_clf, average='macro', zero_division=0)
    joblib.dump(lgb_clf, os.path.join(MODEL_DIR, "lgb_classifier.pkl"))
    results['LGB_Classifier'] = f"Accuracy: {acc_lgb_clf:.4f} | Macro F1: {f1_lgb_clf:.4f}"
    
    cm_lgb = confusion_matrix(y_val_clf, preds_lgb_clf, labels=range(len(unique_targets)))
    sns.heatmap(cm_lgb, annot=True, fmt='d', cmap='Blues', ax=axes_clf[0, 0],
                xticklabels=class_names, yticklabels=class_names)
    axes_clf[0, 0].set_title(f"LGB Classifier 오차 행렬 (F1: {f1_lgb_clf:.4f})", fontsize=13, fontweight='bold')
    
    importances_lgb_split = lgb_clf.booster_.feature_importance(importance_type='split')
    indices_lgb_split = np.argsort(importances_lgb_split)[::-1][:15]
    y_labels_lgb = np.array(feature_cols)[indices_lgb_split]
    sns.barplot(x=importances_lgb_split[indices_lgb_split], y=y_labels_lgb, hue=y_labels_lgb, palette='viridis', legend=False, ax=axes_clf[0, 1])
    axes_clf[0, 1].set_title("LGBM 급등주 포착 기여도 (Split 기준)", fontsize=13, fontweight='bold')
    
    importances_lgb_gain = lgb_clf.booster_.feature_importance(importance_type='gain')
    indices_lgb_gain = np.argsort(importances_lgb_gain)[::-1][:15]
    y_labels_lgb_g = np.array(feature_cols)[indices_lgb_gain]
    sns.barplot(x=importances_lgb_gain[indices_lgb_gain], y=y_labels_lgb_g, hue=y_labels_lgb_g, palette='mako', legend=False, ax=axes_clf[0, 2])
    axes_clf[0, 2].set_title("LGBM 매매포착 실질 기여도 (Gain 기준)", fontsize=13, fontweight='bold')

    # ==========================================
    # 4. Model 2: XGBoost Classifier
    # ==========================================
    print("▶ [3/7] 학습 진행중... XGBoost Classifier")
    xgb_clf = XGBClassifier(n_estimators=300, learning_rate=0.05, max_depth=6, random_state=42, eval_metric='mlogloss')
    xgb_clf.fit(X_train, y_train_clf, sample_weight=sample_weights_train)
    preds_xgb_clf = xgb_clf.predict(X_val)
    
    acc_xgb_clf = accuracy_score(y_val_clf, preds_xgb_clf)
    f1_xgb_clf = f1_score(y_val_clf, preds_xgb_clf, average='macro', zero_division=0)
    joblib.dump(xgb_clf, os.path.join(MODEL_DIR, "xgb_classifier.pkl"))
    results['XGB_Classifier'] = f"Accuracy: {acc_xgb_clf:.4f} | Macro F1: {f1_xgb_clf:.4f}"
    
    cm_xgb = confusion_matrix(y_val_clf, preds_xgb_clf, labels=range(len(unique_targets)))
    sns.heatmap(cm_xgb, annot=True, fmt='d', cmap='Oranges', ax=axes_clf[1, 0],
                xticklabels=class_names, yticklabels=class_names)
    axes_clf[1, 0].set_title(f"XGB Classifier 오차 행렬 (F1: {f1_xgb_clf:.4f})", fontsize=13, fontweight='bold')
    
    importances_xgb_weight = xgb_clf.get_booster().get_score(importance_type='weight')
    imp_xgb_w = np.array([importances_xgb_weight.get(f"f{feature_cols.index(c)}", importances_xgb_weight.get(c, 0)) for c in feature_cols])
    indices_xgb_w = np.argsort(imp_xgb_w)[::-1][:15]
    y_labels_xgb_w = np.array(feature_cols)[indices_xgb_w]
    sns.barplot(x=imp_xgb_w[indices_xgb_w], y=y_labels_xgb_w, hue=y_labels_xgb_w, palette='rocket', legend=False, ax=axes_clf[1, 1])
    axes_clf[1, 1].set_title("XGBoost 급등주 포착 기여도 (Weight 기준)", fontsize=13, fontweight='bold')
    
    importances_xgb_gain = xgb_clf.get_booster().get_score(importance_type='gain')
    imp_xgb_g = np.array([importances_xgb_gain.get(f"f{feature_cols.index(c)}", importances_xgb_gain.get(c, 0)) for c in feature_cols])
    indices_xgb_g = np.argsort(imp_xgb_g)[::-1][:15]
    y_labels_xgb_g = np.array(feature_cols)[indices_xgb_g]
    sns.barplot(x=imp_xgb_g[indices_xgb_g], y=y_labels_xgb_g, hue=y_labels_xgb_g, palette='flare', legend=False, ax=axes_clf[1, 2])
    axes_clf[1, 2].set_title("XGBoost 매매포착 실질 기여도 (Gain 기준)", fontsize=13, fontweight='bold')

    plt.suptitle("분류 모델(Classifier) 기여도 및 오차행렬 종합 분석표", fontsize=20, fontweight='bold', y=0.98)
    plt.tight_layout()
    clf_plot_path = os.path.join(RESULT_DIR, "classifier_performance_evaluation.png")
    plt.savefig(clf_plot_path, dpi=250)
    plt.close()
    print(f"▶ [4/7] 분류 모델 분석 차트 이미지 저장 완료: {clf_plot_path}")

    # ----------------------------------------------------
    # 5~6. 회귀 모델 학습 및 산점도 출력
    # ----------------------------------------------------
    fig_reg, axes_reg = plt.subplots(1, 2, figsize=(18, 8))
    
    print("\n▶ [5/7] 학습 진행중... LightGBM Regressor")
    lgb_reg = LGBMRegressor(n_estimators=300, learning_rate=0.05, max_depth=6, random_state=42, verbose=-1)
    lgb_reg.fit(X_train, y_train_reg)
    preds_lgb_reg = lgb_reg.predict(X_val)
    mse_lgb_reg = mean_squared_error(y_val_reg, preds_lgb_reg)
    r2_lgb_reg = r2_score(y_val_reg, preds_lgb_reg)
    joblib.dump(lgb_reg, os.path.join(MODEL_DIR, "lgb_regressor.pkl"))
    results['LGB_Regressor'] = f"MSE: {mse_lgb_reg:.5f}, R2: {r2_lgb_reg:.4f}"
    
    axes_reg[0].scatter(y_val_reg, preds_lgb_reg, alpha=0.3, color='blue')
    axes_reg[0].plot([y_val_reg.min(), y_val_reg.max()], [y_val_reg.min(), y_val_reg.max()], 'r--', lw=2)
    axes_reg[0].set_title(f"LGB Regressor 실제 vs 예측 (R2: {r2_lgb_reg:.4f})")
    
    print("▶ [6/7] 학습 진행중... XGBoost Regressor")
    xgb_reg = XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6, random_state=42)
    xgb_reg.fit(X_train, y_train_reg)
    preds_xgb_reg = xgb_reg.predict(X_val)
    mse_xgb_reg = mean_squared_error(y_val_reg, preds_xgb_reg)
    r2_xgb_reg = r2_score(y_val_reg, preds_xgb_reg)
    joblib.dump(xgb_reg, os.path.join(MODEL_DIR, "xgb_regressor.pkl"))
    results['XGB_Regressor'] = f"MSE: {mse_xgb_reg:.5f}, R2: {r2_xgb_reg:.4f}"
    
    axes_reg[1].scatter(y_val_reg, preds_xgb_reg, alpha=0.3, color='orange')
    axes_reg[1].plot([y_val_reg.min(), y_val_reg.max()], [y_val_reg.min(), y_val_reg.max()], 'r--', lw=2)
    axes_reg[1].set_title(f"XGB Regressor 실제 vs 예측 (R2: {r2_xgb_reg:.4f})")
    
    reg_plot_path = os.path.join(RESULT_DIR, "regressor_performance_evaluation.png")
    plt.tight_layout()
    plt.savefig(reg_plot_path, dpi=250)
    plt.close()
    print(f"▶ 회귀 모델 분석 차트 이미지 저장 완료: {reg_plot_path}")

    print("\n================ [7/7] 모델 검증 결과 종합 비교 ================")
    for model_name, score in results.items():
        print(f" {model_name:<15} : {score}")
    print("=================================================================")