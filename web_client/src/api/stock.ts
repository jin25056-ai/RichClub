import apiClient from './client';

// 타입
export interface AIPredictionItem {
  stock_code: string;
  stock_name: string;
  current_price: number | null;
  change_pct: number | null;
  signal: string;
  signal_label: number;
  confidence: number | null;
  predicted_at: string;
}

export interface AIDetailResponse {
  stock_code: string;
  stock_name: string;
  signal: string;
  confidence: number | null;
  feature_importance: { feature: string; importance: number }[];
  conditions_met: string[];
  conditions_not_met: string[];
  predicted_at: string;
}

export interface RSIDataPoint { date: string; rsi: number; }
export interface RSIResponse {
  stock_code: string;
  stock_name: string;
  period: string;
  data: RSIDataPoint[];
}

export interface MACDDataPoint { date: string; macd: number; signal: number; histogram: number; }
export interface MACDResponse {
  stock_code: string;
  stock_name: string;
  period: string;
  data: MACDDataPoint[];
}

export interface CandleDataPoint {
  datetime: string;
  open: number; high: number; low: number; close: number; volume: number;
}
export interface CandleResponse { stock_code: string; interval: string; data: CandleDataPoint[]; }

export interface GlobalMarketItem {
  symbol: string; name: string;
  price: number | null; change_pct: number | null; trend: string;
}
export interface GlobalMarketResponse {
  updated_at: string;
  items: GlobalMarketItem[];
  invest_signal: string;
  invest_reason: string;
}

export interface TradeRecord {
  buy_date: string;
  buy_price: number;
  sell_date: string | null;
  sell_price: number | null;
  return_pct: number | null;
  unrealized_pct: number | null;
}

export interface WinRateResult {
  signal: string;
  total_signals: number;
  win_count: number;
  lose_count: number;
  win_rate: number;
  avg_return_pct: number;
  max_return_pct: number;
  max_loss_pct: number;
  cumulative_return_pct: number;
  unrealized_pct: number | null;
  hold_days: number;
}
export interface WinRateResponse {
  stock_code: string | null;
  stock_name: string | null;
  period: string;
  results: WinRateResult[];
  trades: TradeRecord[];
  updated_at: string;
}

export interface StockItem { stock_code: string; stock_name: string; }
export interface StockSearchResult { stock_code: string; stock_name: string; }

// API 함수
export const stockApi = {
  search: (q: string) =>
    apiClient.get<StockItem[]>('/api/v1/stock/search', { params: { q } }),

  getPredictions: (signal?: string, limit = 50, stock_name?: string) =>
    apiClient.get<AIPredictionItem[]>('/api/v1/stock/ai/predictions', {
      params: { signal, limit, stock_name },
    }),

  getTodayPredictions: (signal?: string) =>
    apiClient.get<AIPredictionItem[]>('/api/v1/stock/ai/today', {
      params: { signal },
    }),

  getAIDetail: (stock_code: string) =>
    apiClient.get<AIDetailResponse>(`/api/v1/stock/ai/detail/${stock_code}`),

  getRSI: (stock_code: string, period = '3m') =>
    apiClient.get<RSIResponse>(`/api/v1/stock/chart/rsi/${stock_code}`, { params: { period } }),

  getMACD: (stock_code: string, period = '3m') =>
    apiClient.get<MACDResponse>(`/api/v1/stock/chart/macd/${stock_code}`, { params: { period } }),

  getCandles: (stock_code: string, days = 1) =>
    apiClient.get<CandleResponse>(`/api/v1/stock/chart/candle/${stock_code}`, { params: { days } }),
};

export const marketApi = {
  getGlobal: () => apiClient.get<GlobalMarketResponse>('/api/v1/market/global'),

  getWinRate: (params?: { stock_code?: string; period?: string; hold_days?: number; start_date?: string; end_date?: string }) =>
    apiClient.get<WinRateResponse>('/api/v1/market/winrate', { params }),
};
