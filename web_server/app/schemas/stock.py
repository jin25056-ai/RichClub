from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# 종목
class StockItem(BaseModel):
    stock_code: str
    stock_name: str


class StockSearchResult(BaseModel):
    stock_code: str
    stock_name: str


# AI 예측
class AIPredictionItem(BaseModel):
    stock_code: str
    stock_name: str
    current_price: Optional[float] = None
    change_pct: Optional[float] = None   # 전일 대비 변화율 (%)
    signal: str                          # 매수 / 매도 / 관망
    signal_label: int                    # 0=매도 1=매수 2=관망
    confidence: Optional[float] = None
    predicted_at: Optional[datetime] = None


class AIDetailResponse(BaseModel):
    stock_code: str
    stock_name: str
    signal: str
    confidence: Optional[float] = None
    feature_importance: List[dict]
    conditions_met: List[str]
    conditions_not_met: List[str]
    predicted_at: Optional[datetime] = None


# RSI
class RSIDataPoint(BaseModel):
    date: str
    rsi: float


class RSIResponse(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    period: str
    data: List[RSIDataPoint]


# MACD
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


# 공시
class DisclosureItem(BaseModel):
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    disclosure_type: str
    title: str
    disclosed_at: datetime
    url: str


# 매매일지
class TradeLogCreate(BaseModel):
    stock_code: str
    stock_name: str
    trade_type: str
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
