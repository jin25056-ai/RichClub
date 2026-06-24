"""
app/api/v1/mlops.py - MLOps 대시보드 API
"""
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.db.mongo import get_db

router = APIRouter(prefix="/mlops", tags=["mlops"])


def _db() -> AsyncIOMotorDatabase:
    return get_db()


class ModelStatus(BaseModel):
    model_exists: bool
    last_trained_at: Optional[datetime]
    last_accuracy: Optional[float]
    total_signals: int
    returns_calculated: int
    pending_returns: int


class MonthlyPerf(BaseModel):
    month: str
    signal: str
    total: int
    correct: int
    accuracy: float
    avg_ret_5d: float
    avg_ret_1d: float


@router.get("/status", response_model=ModelStatus)
async def get_status(
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    from app.ml.trainer import MODEL_PATH
    model_exists = os.path.exists(MODEL_PATH)
    last_train = await db.model_train_history.find_one(sort=[("trained_at", -1)])
    total = await db.total_trading_signals.count_documents({})
    calculated = await db.total_trading_signals.count_documents({'ret_5d': {'$ne': None}})
    cutoff = datetime.utcnow() - timedelta(days=5)
    pending = await db.total_trading_signals.count_documents({
        'ret_5d': None, 'close': {'$ne': None},
        'predicted_at': {'$lte': cutoff}
    })
    return ModelStatus(
        model_exists=model_exists,
        last_trained_at=last_train.get('trained_at') if last_train else None,
        last_accuracy=last_train.get('accuracy') if last_train else None,
        total_signals=total,
        returns_calculated=calculated,
        pending_returns=pending,
    )


@router.get("/monthly-performance", response_model=List[MonthlyPerf])
async def get_monthly_performance(
    months: int = 12,
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """월별 신호 성능 (model_performance_monthly 컬렉션)"""
    cursor = db.model_performance_monthly.find().sort([("year", -1), ("month_num", -1)]).limit(months * 3)
    result = []
    async for doc in cursor:
        result.append(MonthlyPerf(
            month=doc.get('month', ''),
            signal=doc.get('signal', ''),
            total=doc.get('total', 0),
            correct=doc.get('correct', 0),
            accuracy=doc.get('accuracy', 0),
            avg_ret_5d=doc.get('avg_ret_5d', 0),
            avg_ret_1d=doc.get('avg_ret_1d', 0),
        ))
    return result


@router.get("/signal-stats")
async def get_signal_stats(
    days: int = 90,
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """매수→매도 실현 수익률 기반 기간별 성능"""
    since = datetime.utcnow() - timedelta(days=days)
    pipeline = [
        {'$match': {'signal': '매수', 'ret_realized': {'$ne': None}, 'predicted_at': {'$gte': since}}},
        {'$group': {
            '_id': None,
            'total': {'$sum': 1},
            'correct': {'$sum': {'$cond': ['$is_correct', 1, 0]}},
            'avg_ret': {'$avg': '$ret_realized'},
            'max_ret': {'$max': '$ret_realized'},
            'min_ret': {'$min': '$ret_realized'},
        }},
    ]
    result = []
    async for row in db.total_trading_signals.aggregate(pipeline):
        total = row['total']
        correct = row['correct']
        result.append({
            'total': total,
            'correct': correct,
            'accuracy': round(correct / total * 100, 1) if total > 0 else 0,
            'avg_ret': round(row.get('avg_ret') or 0, 2),
            'max_ret': round(row.get('max_ret') or 0, 2),
            'min_ret': round(row.get('min_ret') or 0, 2),
        })
    return result[0] if result else {'total': 0, 'correct': 0, 'accuracy': 0, 'avg_ret': 0, 'max_ret': 0, 'min_ret': 0}


@router.get("/recent-signals")
async def get_recent_signals(
    days: int = 7,
    signal: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """최근 예측 신호 목록 (수익률 포함)"""
    since = datetime.utcnow() - timedelta(days=days)
    query = {'predicted_at': {'$gte': since}}
    if signal:
        query['signal'] = signal
    cursor = db.total_trading_signals.find(query).sort('predicted_at', -1).limit(200)
    result = []
    async for doc in cursor:
        result.append({
            'stock_name': doc.get('stock_name'),
            'stock_code': doc.get('stock_code'),
            'signal': doc.get('signal'),
            'predicted_at': doc.get('predicted_at'),
            'close': doc.get('close'),
            'ret_1d': doc.get('ret_1d'),
            'ret_5d': doc.get('ret_5d'),
            'ret_20d': doc.get('ret_20d'),
            'ret_60d': doc.get('ret_60d'),
            'is_correct_5d': doc.get('is_correct_5d'),
        })
    return result


@router.get("/train-history")
async def get_train_history(
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    cursor = db.model_train_history.find().sort("trained_at", -1).limit(20)
    result = []
    async for doc in cursor:
        result.append({
            'trained_at': doc.get('trained_at'),
            'triggered_by': doc.get('triggered_by', 'unknown'),
            'accuracy': doc.get('accuracy', 0),
            'n_train': doc.get('n_train', 0),
            'elapsed_sec': doc.get('elapsed_sec', 0),
            'stocks_used': doc.get('stocks_used', 0),
        })
    return result


@router.get("/stock-performance")
async def get_stock_performance(
    days: int = 90,
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """종목별 매수→매도 실현 수익률 집계"""
    from collections import defaultdict
    since = datetime.utcnow() - timedelta(days=days) if days < 9999 else None

    match = {'signal': {'$in': ['매수', '매도']}}
    if since:
        match['predicted_at'] = {'$gte': since}

    cursor = db.total_trading_signals.find(match).sort('predicted_at', 1)
    docs = [doc async for doc in cursor]

    sc_docs = defaultdict(list)
    for doc in docs:
        code = doc.get('stock_code', '')
        if code:
            sc_docs[code].append(doc)

    result = []
    for code, sdocs in sc_docs.items():
        name = sdocs[0].get('stock_name', '')
        position = None
        realized = []
        unrealized_pct = None

        for doc in sdocs:
            signal = doc.get('signal')
            close = doc.get('close')
            predicted_at = doc.get('predicted_at')
            if close is None:
                continue
            close = float(close)
            date_str = predicted_at.strftime('%Y-%m-%d') if hasattr(predicted_at, 'strftime') else str(predicted_at)[:10]

            if signal == '매수' and position is None:
                position = {'buy_date': date_str, 'buy_price': close}
            elif signal == '매도' and position is not None:
                ret = round((close - position['buy_price']) / position['buy_price'] * 100, 2)
                realized.append(ret)
                position = None

        if position is not None:
            latest = sdocs[-1].get('close')
            if latest:
                unrealized_pct = round((float(latest) - position['buy_price']) / position['buy_price'] * 100, 2)

        if not realized:
            continue

        win = [r for r in realized if r > 0]
        cumulative = 1.0
        for r in realized:
            cumulative *= (1 + r / 100)

        result.append({
            'stock_code': code,
            'stock_name': name,
            'total': len(realized),
            'win': len(win),
            'accuracy': round(len(win) / len(realized) * 100, 1) if realized else 0,
            'avg_ret': round(sum(realized) / len(realized), 2) if realized else 0,
            'cumulative_ret': round((cumulative - 1) * 100, 2) if realized else 0,
            'max_ret': round(max(realized), 2) if realized else 0,
            'min_ret': round(min(realized), 2) if realized else 0,
            'unrealized_pct': unrealized_pct,
        })

    result.sort(key=lambda x: x['cumulative_ret'], reverse=True)
    return result[:100]
async def trigger_calculate_returns(
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(_db),
    _: dict = Depends(get_current_user),
):
    """수익률 계산 + 월별 집계 수동 실행"""
    from app.ml.predictor import calculate_returns, aggregate_monthly_performance
    async def run():
        await calculate_returns(db)
        await aggregate_monthly_performance(db)
    background_tasks.add_task(run)
    return {'status': 'started'}


@router.post("/train")
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
