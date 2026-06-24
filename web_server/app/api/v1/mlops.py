"""
app/api/v1/mlops.py

MLOps 대시보드 API
- 모델 성능 모니터링
- 학습 이력 조회
- 수동 재학습 트리거
"""
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.db.mongo import get_db

router = APIRouter(prefix="/mlops", tags=["mlops"])


def _db() -> AsyncIOMotorDatabase:
    return get_db()


class ModelTrainHistory(BaseModel):
    trained_at: Optional[datetime]
    triggered_by: str
    accuracy: float
    n_train: int
    n_test: int
    elapsed_sec: float
    stocks_used: int
    label_dist: dict


class PredictionStats(BaseModel):
    signal: str
    total: int
    evaluated: int
    correct: int
    accuracy: float
    avg_return_pct: float


class ModelStatus(BaseModel):
    model_exists: bool
    model_path: str
    last_trained_at: Optional[datetime]
    last_accuracy: Optional[float]
    total_predictions: int
    pending_evaluation: int


@router.get("/status", response_model=ModelStatus, summary="모델 현황")
async def get_model_status(
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    from app.ml.trainer import MODEL_PATH
    model_exists = os.path.exists(MODEL_PATH)

    last_train = await db.model_train_history.find_one(sort=[("trained_at", -1)])
    total_preds = await db.model_predictions.count_documents({})
    pending = await db.model_predictions.count_documents({'evaluated': False})

    return ModelStatus(
        model_exists=model_exists,
        model_path=MODEL_PATH,
        last_trained_at=last_train.get('trained_at') if last_train else None,
        last_accuracy=last_train.get('accuracy') if last_train else None,
        total_predictions=total_preds,
        pending_evaluation=pending,
    )


@router.get("/train-history", response_model=List[ModelTrainHistory], summary="학습 이력")
async def get_train_history(
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    cursor = db.model_train_history.find().sort("trained_at", -1).limit(20)
    result = []
    async for doc in cursor:
        result.append(ModelTrainHistory(
            trained_at=doc.get('trained_at'),
            triggered_by=doc.get('triggered_by', 'unknown'),
            accuracy=doc.get('accuracy', 0),
            n_train=doc.get('n_train', 0),
            n_test=doc.get('n_test', 0),
            elapsed_sec=doc.get('elapsed_sec', 0),
            stocks_used=doc.get('stocks_used', 0),
            label_dist=doc.get('label_dist', {}),
        ))
    return result


@router.get("/prediction-stats", response_model=List[PredictionStats], summary="예측 성능 통계")
async def get_prediction_stats(
    days: int = 30,
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {'$match': {'predicted_at': {'$gte': since}, 'evaluated': True}},
        {'$group': {
            '_id': '$signal',
            'total': {'$sum': 1},
            'correct': {'$sum': {'$cond': ['$is_correct', 1, 0]}},
            'avg_return': {'$avg': '$actual_return_pct'},
        }},
    ]
    result = []
    async for row in db.model_predictions.aggregate(pipeline):
        total = row['total']
        correct = row['correct']
        result.append(PredictionStats(
            signal=row['_id'],
            total=total,
            evaluated=total,
            correct=correct,
            accuracy=round(correct / total * 100, 1) if total > 0 else 0,
            avg_return_pct=round(row.get('avg_return') or 0, 2),
        ))
    return result


@router.get("/recent-predictions", summary="최근 예측 목록 (평가 포함)")
async def get_recent_predictions(
    days: int = 7,
    signal: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = {'predicted_at': {'$gte': since}}
    if signal:
        query['signal'] = signal
    cursor = db.model_predictions.find(query).sort("predicted_at", -1).limit(200)
    result = []
    async for doc in cursor:
        result.append({
            'stock_name': doc.get('stock_name'),
            'stock_code': doc.get('stock_code'),
            'signal': doc.get('signal'),
            'predicted_at': doc.get('predicted_at'),
            'close_at_prediction': doc.get('close_at_prediction'),
            'actual_return_pct': doc.get('actual_return_pct'),
            'is_correct': doc.get('is_correct'),
            'evaluated': doc.get('evaluated', False),
        })
    return result


@router.post("/train", summary="모델 수동 재학습")
async def trigger_train(
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    from app.ml.trainer import train_model
    try:
        result = await train_model(db, triggered_by="manual_api")
        return {'status': 'success', **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate", summary="예측 성능 수동 평가")
async def trigger_evaluate(
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    from app.ml.predictor import evaluate_predictions
    background_tasks.add_task(evaluate_predictions, db)
    return {'status': 'started', 'message': '백그라운드에서 평가 중. 잠시 후 새로고침하세요.'}
