from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── 종목 ──────────────────────────────────────────────
class StockItem(BaseModel):
    stock_code: str
    stock_name: str


class StockSearchResult(BaseModel):
    stock_code: str
    stock_name: str


# ── AI 예측 ───────────────────────────────────────────
class AIPredictionItem(BaseModel):
    stock_code: str
    stock_name: str
    current_price: Optional[float] = None
    signal: str                   # 매수 / 매도 / 관망
    signal_label: int             # 0=매도 1=매수 2=관망
    confidence: Optional[float] = None   # AI 신뢰도 (0~1)
    predicted_at: Optional[datetime] = None


class AIDetailResponse(BaseModel):
    """AI 분석 상세 - 매수 근거 포함"""
    stock_code: str
    stock_name: str
    signal: str
    confidence: Optional[float] = None
    feature_importance: List[dict]   # [{"feature": "macd", "value": 0.32, "direction": "positive"}, ...]
    conditions_met: List[str]        # 충족된 조건 목록
    conditions_not_met: List[str]    # 미충족 조건 목록
    predicted_at: Optional[datetime] = None


# ── RSI ───────────────────────────────────────────────
class RSIDataPoint(BaseModel):
    date: str
    rsi: float


class RSIResponse(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    period: str          # "1m" / "3m" / "6m"
    data: List[RSIDataPoint]


# ── MACD ──────────────────────────────────────────────
class MACDDataPoint(BaseModel):
    date: str
    macd: float
    signal: float
    histogram: float


class MACDResponse(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    period: str
    data: List[MACDDataPoint]


# ── 공시 ──────────────────────────────────────────────
class DisclosureItem(BaseModel):
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    disclosure_type: str     # 수시공시 / 공시정정 등
    title: str
    disclosed_at: datetime
    url: str


# ── 매매일지 ──────────────────────────────────────────
class TradeLogCreate(BaseModel):
    stock_code: str
    stock_name: str
    trade_type: str       # 매수 / 매도
    price: float
    quantity: float
    memo: Optional[str] = None


class TradeLogItem(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    trade_type: str
    price: float
    quantity: float
    total_amount: float
    memo: Optional[str] = None
    traded_at: datetime
