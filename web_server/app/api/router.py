from fastapi import APIRouter

from app.api.v1 import auth, stock, trade_log

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(stock.router)
router.include_router(trade_log.router)
