import apiClient from './client';

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
export interface RSIResponse { stock_code: string; stock_name: string; period: string; data: RSIDataPoint[]; }

export interface MACDDataPoint { date: string; macd: number; signal: number; histogram: number; }
export interface MACDResponse { stock_code: string; stock_name: string; period: string; data: MACDDataPoint[]; }

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
  stock_code?: string; stock_name?: string;
  buy_date: string; buy_price: number;
  sell_date: string | null; sell_price: number | null;
  return_pct: number | null; unrealized_pct: number | null;
  cash_after?: number | null;  // 청산 후 현금 잔액
  buy_total?: number | null;   // 실제 투자금

  cash_after?: number | null;

}

export interface WinRateResult {
  signal: string; total_signals: number; win_count: number; lose_count: number;
  win_rate: number; avg_return_pct: number; max_return_pct: number;
  max_loss_pct: number; cumulative_return_pct: number;
  unrealized_pct: number | null; hold_days: number;
}

export interface WinRateResponse {
  stock_code: string | null; stock_name: string | null; period: string;
  results: WinRateResult[]; trades: TradeRecord[]; updated_at: string;
}

export interface HoldingItem {
  stock_code: string; stock_name: string;
  buy_date: string; buy_price: number;
  current_price: number; unrealized_pct: number;
}

export interface PerformanceResponse {
  model_id: string;
  period: string;
  year?: number;
  win_rate: number;
  cumulative_return_pct: number;
  total_trades: number;
  win_count: number;
  lose_count: number;
  avg_return_pct: number;
  max_return_pct: number;
  max_loss_pct: number;
  holdings: HoldingItem[];
  trades: TradeRecord[];
  updated_at: string;
}

export interface SimYearResult {
  year: number;
  total_trades: number;
  win_count: number;
  lose_count: number;
  win_rate: number;
  avg_return_pct: number;
  final_amount: number;
  profit: number;
  return_pct: number;
}

export interface SimulationResponse {
  model_id: string;
  principal: number;
  max_stocks: number;
  years: SimYearResult[];
  total_final_amount: number;
  total_profit: number;
  total_return_pct: number;
  updated_at: string;
}

export interface RecommendItem {
  stock_code: string;
  stock_name: string;
  model_name: string;
  pred_score: number;
  close: number | null;
}

export interface RecommendResponse {
  date: string;
  total: number;
  items: RecommendItem[];
  updated_at: string;
}

export interface StockItem { stock_code: string; stock_name: string; }
export interface StockSearchResult { stock_code: string; stock_name: string; }

export interface WatchlistItem {
  id: string;
  stock_code: string;
  stock_name: string;
  memo: string | null;
  added_at: string;
  signal: string | null;
  confidence: number | null;
  current_price: number | null;
}

export interface TradeLogItem {
  id: string;
  stock_code: string;
  stock_name: string;
  trade_type: 'buy' | 'sell';
  price: number;
  quantity: number;
  total_amount: number;
  memo: string | null;
  traded_at: string;
}

export interface TradeLogCreate {
  stock_code: string;
  stock_name: string;
  trade_type: 'buy' | 'sell';
  price: number;
  quantity: number;
  memo?: string;
}

const DEFAULT_MODEL = 'ju-model-v2';

export const stockApi = {
  search: (q: string) =>
    apiClient.get<StockItem[]>('/api/v1/stock/search', { params: { q } }),

  getPredictions: (signal?: string, limit = 50, modelId = DEFAULT_MODEL, stock_name?: string) =>
    apiClient.get<AIPredictionItem[]>('/api/v1/stock/ai/predictions', {
      params: { signal, limit, stock_name, model_id: modelId },
    }),

  getTodayPredictions: (signal?: string, modelId = DEFAULT_MODEL) =>
    apiClient.get<AIPredictionItem[]>('/api/v1/stock/ai/today', {
      params: { signal, model_id: modelId },
    }),

  getAIDetail: (stock_code: string, modelId = DEFAULT_MODEL) =>
    apiClient.get<AIDetailResponse>(`/api/v1/stock/ai/detail/${stock_code}`, {
      params: { model_id: modelId },
    }),

  getRSI: (stock_code: string, period = 'all') =>
    apiClient.get<RSIResponse>(`/api/v1/stock/chart/rsi/${stock_code}`, { params: { period } }),

  getMACD: (stock_code: string, period = 'all') =>
    apiClient.get<MACDResponse>(`/api/v1/stock/chart/macd/${stock_code}`, { params: { period } }),

  getCandles: (stock_code: string, days = 0, modelId = DEFAULT_MODEL) =>
    apiClient.get<CandleResponse>(`/api/v1/stock/chart/candle/${stock_code}`, {
      params: { days, model_id: modelId },
    }),

  getCandles5m: (stock_code: string, days = 1) =>
    apiClient.get<CandleResponse>(`/api/v1/stock/chart/candle5m/${stock_code}`, { params: { days } }),

  getPrice: (stock_code: string) =>
    apiClient.get<{ stock_code: string; stock_name: string; close: number; predicted_at: string }>(`/api/v1/stock/price/${stock_code}`),

  getIndicatorSignals: () =>
    apiClient.get<{
      stock_code: string; stock_name: string; signal: string; score: number;
      reasons: string[]; rsi: number | null; ma_align: string;
      macd_bull: boolean | null; close: number | null;
    }[]>('/api/v1/stock/indicator-signals'),

  getNews: (query?: string) =>
    apiClient.get<{
      items: {
        title: string;
        originallink: string;
        link: string;
        description: string;
        pubDate: string;
      }[];
    }>('/api/v1/news', { params: { query: query ?? '주식 증권', display: 20 } }),

  getTodaySignals: (days = 1, modelId = DEFAULT_MODEL) =>
    apiClient.get<{
      stock_code: string; stock_name: string;
      signal: string; sub: string;
      tags: { label: string; color: string }[];
      close: number | null; rsi: number | null;
      ma_align: string; macd_bull: boolean | null;
    }[]>('/api/v1/stock/today-signals', { params: { days, model_id: modelId } }),
};

export const marketApi = {
  getGlobal: () =>
    apiClient.get<GlobalMarketResponse>('/api/v1/market/global'),

  getWinRate: (params?: { stock_code?: string; period?: string; hold_days?: number; start_date?: string; end_date?: string; model_id?: string }) =>
    apiClient.get<WinRateResponse>('/api/v1/market/winrate', { params }),

  getWinRateCombined: (params?: { stock_code?: string; period?: string; hold_days?: number; start_date?: string; end_date?: string; model_id?: string }) =>
    apiClient.get<WinRateResponse>('/api/v1/market/winrate/combined', { params }),

  getWinRateIndicator: (params?: { stock_code?: string; period?: string; hold_days?: number; start_date?: string; end_date?: string }) =>
    apiClient.get<WinRateResponse>('/api/v1/market/winrate/indicator', { params }),

  getWinRateSimple: (params?: { stock_code?: string; period?: string; hold_days?: number; start_date?: string; end_date?: string; model_id?: string }) =>
    apiClient.get<WinRateResponse>('/api/v1/market/winrate/simple', { params }),

  getPerformance: (model_id: string, period?: string, year?: number) =>
    apiClient.get<PerformanceResponse>(`/api/v1/market/performance/${model_id}`, { params: { period, year } }),

  getSimulation: (model_id: string, principal: number, max_stocks: number, year?: number) =>
    apiClient.get<SimulationResponse>(`/api/v1/market/simulation/${model_id}`, { params: { principal, max_stocks, year } }),

  getSimulationDetail: (model_id: string, year: number, max_stocks: number) =>
    apiClient.get<WinRateResponse>(`/api/v1/market/simulation-detail/${model_id}`, { params: { year, max_stocks } }),

  getRecommend: (target_date?: string) =>
    apiClient.get<RecommendResponse>('/api/v1/market/recommend', { params: { target_date } }),
};

export const watchlistApi = {
  get: () =>
    apiClient.get<WatchlistItem[]>('/api/v1/watchlist'),

  check: (stock_code: string) =>
    apiClient.get<{ is_watching: boolean; id: string | null }>(`/api/v1/watchlist/check/${stock_code}`),

  add: (stock_code: string, stock_name: string, memo?: string) =>
    apiClient.post<WatchlistItem>('/api/v1/watchlist', { stock_code, stock_name, memo }),

  remove: (id: string) =>
    apiClient.delete(`/api/v1/watchlist/${id}`),
};

export const tradeLogApi = {
  get: () =>
    apiClient.get<TradeLogItem[]>('/api/v1/trade-log'),

  getTrash: () =>
    apiClient.get<TradeLogItem[]>('/api/v1/trade-log/trash'),

  create: (data: TradeLogCreate) =>
    apiClient.post<TradeLogItem>('/api/v1/trade-log', data),

  update: (id: string, data: { price?: number; quantity?: number; memo?: string }) =>
    apiClient.patch<TradeLogItem>(`/api/v1/trade-log/${id}`, data),

  remove: (id: string) =>
    apiClient.delete(`/api/v1/trade-log/${id}`),

  restore: (id: string) =>
    apiClient.post<TradeLogItem>(`/api/v1/trade-log/${id}/restore`),

  permanentDelete: (id: string) =>
    apiClient.delete(`/api/v1/trade-log/${id}/permanent`),
};
