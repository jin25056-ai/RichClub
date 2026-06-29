# RichClub AI 예측 모델 추가 가이드

## 현재 모델 목록

| model_id | 설명 | 예측 시각 (KST) |
|---|---|---|
| ju-model-v2 | 기본 XGBoost 예측 모델 | 15:35 |
| seo-model-v1 | LightGBM + XGBoost 앙상블 v1 | 15:40 |
| seo-model-v2 | LightGBM + XGBoost 앙상블 v2 | 15:45 |

---

## 새 모델 추가 절차

### 1. 모델 파일 준비

pkl 파일 6개가 필요합니다.

```
lgb_classifier.pkl
lgb_regressor.pkl
xgb_classifier.pkl
xgb_regressor.pkl
model_features.pkl
target_label_map.pkl
```

### 2. 로컬 경로에 pkl 배치

```
web_server/app/models/{model-id}/
```

seo 계열 모델은 train 스크립트가 `train_pklFile/` 하위에 저장하는 경우:

```
web_server/app/models/{model-id}/train_pklFile/
```

### 3. Mac Mini 볼륨 경로에 복사

배포 후에도 파일이 유지되도록 Mac Mini의 볼륨 경로에 복사해야 합니다.

```bash
mkdir -p /Users/nadeko/models/{model-id}
cp -r /Users/nadeko/Desktop/.../models/{model-id}/. /Users/nadeko/models/{model-id}/
```

Docker 볼륨 마운트 설정: `-v /Users/nadeko/models:/app/models`

### 4. seo_predictor.py에 모델 설정 추가

`web_server/app/ml/seo_predictor.py`의 `MODEL_CONFIGS`에 추가합니다.

```python
MODEL_CONFIGS = {
    ...
    "seo-model-v3": {
        "model_dir": "/app/models/seo-model-v3",   # pkl 파일이 있는 실제 경로
        "csv_dir": "/app/collect_data/seojin",
        "csv_encoding": "utf-8-sig",
    },
}
```

pkl이 `train_pklFile/` 하위에 있다면 `model_dir`을 그 경로까지 포함해 지정합니다.

### 5. scheduler/jobs.py에 스케줄 추가

`web_server/app/scheduler/jobs.py`에 함수와 스케줄을 추가합니다.

```python
async def run_daily_seo_v3_predict() -> None:
    """매일 장 마감 후 seo-model-v3 예측 - 데이터 없으면 10분마다 재시도"""
    import yfinance as yf
    from datetime import timedelta
    db = get_db()
    from app.ml.seo_predictor import run_daily_seo_prediction

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d')

    while True:
        raw = yf.download('005930.KS', start=today, end=tomorrow,
                          interval='1d', progress=False, auto_adjust=True)
        if not raw.empty:
            await run_daily_seo_prediction(db, model_id="seo-model-v3", target_date=today)
            break
        await asyncio.sleep(600)
```

`start_scheduler()` 안에 잡 등록 (시간대 겹치지 않게 주의):

```python
scheduler.add_job(run_daily_seo_v3_predict, trigger="cron",
                  day_of_week="mon-fri", hour="6", minute="50",
                  id="daily_seo_v3_predict", replace_existing=True,
                  misfire_grace_time=3600)
```

### 6. models.py에 모델 정보 추가

`web_server/app/api/v1/models.py`의 `ALL_MODELS`에 추가합니다.

```python
{
    "id": "seo-model-v3",
    "name": "seo-model-v3",
    "description": "고성능 AI 예측 모델 v3",
    "required_plan": ["seo-model", "auto-trade"],
},
```

### 7. 초기 전체 예측 실행

배포 후 서버에서 전체 기간 예측을 한 번 돌립니다.

```bash
docker exec richclub-api python3 -c "
import asyncio, logging
logging.basicConfig(level=logging.INFO)
from app.db.mongo import get_db
from app.ml.seo_predictor import run_full_seo_prediction

async def main():
    db = get_db()
    await run_full_seo_prediction(db, model_id='seo-model-v3')

asyncio.run(main())
" 2>&1
```

### 8. push 및 배포

```bash
git add .
git commit -m "feat: add seo-model-v3"
git push origin efforthye
```

Jenkins가 자동으로 빌드 및 배포합니다.

---

## 스케줄 타임라인 (KST)

| 시각 | 작업 |
|---|---|
| 15:35 | ju-model-v2 예측 (데이터 없으면 10분마다 재시도) |
| 15:40 | seo-model-v1 예측 (데이터 없으면 10분마다 재시도) |
| 15:45 | seo-model-v2 예측 (데이터 없으면 10분마다 재시도) |
| 16:00 | 수익률 계산 및 월별 집계 |

---

## 주의사항

- 모델 파일은 git에 포함되지만, Mac Mini 볼륨(`/Users/nadeko/models/`)에도 별도로 복사해야 합니다. Docker 볼륨이 이미지보다 우선합니다.
- CSV 인코딩: seo-model-v1은 `cp949`, seo-model-v2 이후는 `utf-8-sig`를 사용합니다.
- 스케줄 시각이 겹치지 않도록 5분 간격으로 배치합니다.
- pkl 버전 불일치 경고(`InconsistentVersionWarning`)는 무시해도 됩니다. 기능에는 영향 없습니다.
