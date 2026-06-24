"""
app/scheduler/daily_collector.py - predictor.py 위임
"""
from app.ml.predictor import run_daily_prediction, evaluate_predictions

async def collect_daily_signals(db, target_date=None):
    await run_daily_prediction(db, target_date)
