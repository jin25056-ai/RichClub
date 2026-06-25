from fastapi import APIRouter

from app.api.v1 import auth, stock, trade_log, market, watchlist, mlops, news

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(stock.router)
router.include_router(trade_log.router)
router.include_router(market.router)
router.include_router(watchlist.router)
router.include_router(mlops.router)
router.include_router(news.router)
