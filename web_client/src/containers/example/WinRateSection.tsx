import React, { useState, useEffect } from 'react';
import { marketApi, WinRateResult, TradeRecord } from '../../api/stock';

type TabType = 'ai' | 'simple' | 'combined' | 'indicator';

interface Props {
  compact?: boolean;
  stockCode?: string;
  modelId?: string;
  onTabChange?: (tab: 'ai' | 'simple') => void;
}

const fmtKRW = (n: number) => {
  if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(1)}억`;
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(0)}만`;
  return n.toLocaleString();
};

const pctColor = (v: number) => v >= 0 ? '#16a34a' : '#dc2626';
const pctStr = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;

const inputStyle: React.CSSProperties = {
  background: '#1e1e2e', border: '1px solid #2d2d3d',
  borderRadius: 4, padding: '3px 5px', fontSize: 10,
  color: '#e2e8f0', outline: 'none', width: '100%',
};

const TABS: { key: TabType; label: string; desc: string }[] = [
  { key: 'ai',        label: 'AI',      desc: '매수: AI + MA60 상승 / 매도: AI 신호  (침체구간제외)' },
  { key: 'simple',    label: '5일선',   desc: '매수: AI + MA60 상승 / 매도: 5일선 꺾임  (침체구간제외)' },
  { key: 'combined',  label: 'AI+지표', desc: '매수: AI + MA정배열 + MA60상승 / 매도: AI or MA역배열' },
  { key: 'indicator', label: '지표',    desc: '매수: MA정배열+MA60상승 진입 / 매도: MA역배열 (AI 모델 무관)' },
];

const getApiFn = (t: TabType) => {
  if (t === 'simple')    return marketApi.getWinRateSimple;
  if (t === 'combined')  return marketApi.getWinRateCombined;
  if (t === 'indicator') return marketApi.getWinRateIndicator;
  return marketApi.getWinRate;
};

const WinRateSection: React.FC<Props> = ({ compact, stockCode, modelId, onTabChange }) => {
  const [tab, setTab] = useState<TabType>('ai');
  const [period, setPeriod] = useState('3m');
  const [useCustomDate, setUseCustomDate] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [results, setResults] = useState<WinRateResult[]>([]);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [inputAmt, setInputAmt] = useState('1000000');

  const fetchData = (p: string, sc?: string, sd?: string, ed?: string, t: TabType = tab) => {
    setLoading(true);
    const params: any = {
      stock_code: sc || undefined,
      period: p,
      hold_days: 5,
      start_date: sd || undefined,
      end_date: ed || undefined,
    };
    // indicator 탭은 AI 모델과 무관 - model_id 미전달
    if (t !== 'indicator') {
      params.model_id = modelId || 'ju-model-v2';
    }
    getApiFn(t)(params)
      .then((res: { data: { results: WinRateResult[]; trades: TradeRecord[] } }) => {
        setResults(res.data.results);
        setTrades(res.data.trades || []);
      })
      .catch(() => { setResults([]); setTrades([]); })
      .finally(() => setLoading(false));
  };

  const handleTab = (t: TabType) => {
    setTab(t);
    if (t === 'ai' || t === 'simple') onTabChange?.(t);
    fetchData(period, stockCode, useCustomDate ? startDate : undefined, useCustomDate ? endDate : undefined, t);
  };

  useEffect(() => {
    if (stockCode) fetchData(period, stockCode);
  }, [stockCode, modelId]);

  const handlePeriod = (p: string) => {
    setPeriod(p);
    setUseCustomDate(false);
    fetchData(p, stockCode);
  };

  const handleCustomSearch = () => {
    if (!startDate) return;
    setUseCustomDate(true);
    fetchData(period, stockCode, startDate, endDate);
  };

  const r = results[0] ?? null;
  const cumPct = r?.cumulative_return_pct ?? null;
  const completedTrades = trades.filter((t: TradeRecord) => t.return_pct != null);
  const openTrades = trades.filter((t: TradeRecord) => t.unrealized_pct != null);

  const principal = parseFloat(inputAmt.replace(/,/g, '')) || 0;
  const finalAmt = cumPct != null && principal > 0 ? principal * (1 + cumPct / 100) : null;
  const profit = finalAmt != null ? finalAmt - principal : null;

  const activeDesc = TABS.find((c) => c.key === tab)?.desc ?? '';

  if (!compact) return null;

  return (
    <div>
      <div style={{ marginBottom: 4 }}>
        <div style={{ display: 'flex', gap: 3, marginBottom: 4 }}>
          {TABS.map(({ key, label }) => (
            <button key={key} onClick={() => handleTab(key)}
              style={{
                flex: 1, padding: '4px 0', fontSize: 9, borderRadius: 4, border: 'none', cursor: 'pointer',
                background: tab === key ? '#6366f1' : '#1e1e2e',
                color: tab === key ? '#fff' : '#888', fontWeight: tab === key ? 600 : 400,
              }}>{label}</button>
          ))}
        </div>
        <div style={{ fontSize: 9, color: '#4b5563' }}>{activeDesc}</div>
      </div>

      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', gap: 3, marginBottom: 5, alignItems: 'center' }}>
          <span style={{ fontSize: 9, color: '#555' }}>기간</span>
          {(['1m', '3m', '6m', 'all'] as const).map((p) => (
            <button key={p} onClick={() => handlePeriod(p)}
              style={{
                padding: '2px 6px', fontSize: 10, borderRadius: 3, border: 'none', cursor: 'pointer',
                background: period === p && !useCustomDate ? '#6366f1' : '#1e1e2e',
                color: period === p && !useCustomDate ? '#fff' : '#888',
              }}>{p}</button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
          <input value={startDate} onChange={(e) => setStartDate(e.target.value)}
            placeholder="YYMMDD" maxLength={6}
            style={{ ...inputStyle, width: 55, textAlign: 'center' }} />
          <span style={{ fontSize: 9, color: '#555' }}>~</span>
          <input value={endDate} onChange={(e) => setEndDate(e.target.value)}
            placeholder="YYMMDD" maxLength={6}
            style={{ ...inputStyle, width: 55, textAlign: 'center' }} />
          <button onClick={handleCustomSearch}
            style={{
              padding: '2px 8px', fontSize: 10, borderRadius: 3, border: 'none', cursor: 'pointer',
              background: useCustomDate ? '#6366f1' : '#2d2d3d', color: '#fff', flexShrink: 0,
            }}>조회</button>
        </div>
      </div>

      <div style={{ opacity: loading ? 0.4 : 1, transition: 'opacity 0.15s' }}>
        {completedTrades.length === 0 && openTrades.length === 0 && (
          <div style={{ fontSize: 10, color: '#555', textAlign: 'center', padding: '16px 0' }}>
            해당 기간 매수 신호 없음
          </div>
        )}

        {(completedTrades.length > 0 || openTrades.length > 0) && (
          <>
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 9, color: '#555', marginBottom: 5 }}>거래 내역</div>

              {completedTrades.map((t: TradeRecord, i: number) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '5px 8px', marginBottom: 3, borderRadius: 5,
                  background: (t.return_pct ?? 0) >= 0 ? '#14532d22' : '#7f1d1d22',
                }}>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center', fontSize: 9, color: '#6b7280' }}>
                    <span style={{ color: '#16a34a', fontWeight: 600 }}>B</span>
                    <span>{t.buy_date}</span>
                    <span style={{ color: '#555' }}>→</span>
                    <span style={{ color: '#dc2626', fontWeight: 600 }}>S</span>
                    <span>{t.sell_date}</span>
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 700, color: pctColor(t.return_pct ?? 0), flexShrink: 0, marginLeft: 6 }}>
                    {pctStr(t.return_pct ?? 0)}
                  </span>
                </div>
              ))}

              {openTrades.map((t: TradeRecord, i: number) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '5px 8px', marginBottom: 3, borderRadius: 5,
                  background: '#0d0d1a', border: '1px dashed #2d2d3d',
                }}>
                  <div style={{ fontSize: 9, color: '#6b7280' }}>
                    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                      <span style={{ color: '#16a34a', fontWeight: 600 }}>B</span>
                      <span>{t.buy_date}</span>
                      <span style={{ color: '#555' }}>→</span>
                      <span style={{ color: '#555' }}>보유중</span>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: 6 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: pctColor(t.unrealized_pct ?? 0) }}>
                      {pctStr(t.unrealized_pct ?? 0)}
                    </div>
                    <div style={{ fontSize: 8, color: '#4b5563' }}>미실현</div>
                  </div>
                </div>
              ))}
            </div>

            {completedTrades.length > 0 && r && (
              <div style={{
                background: '#0d0d1a', borderRadius: 6, padding: '8px 10px', marginBottom: 10,
                border: `1px solid ${pctColor(cumPct ?? 0)}44`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                  <span style={{ fontSize: 9, color: '#555' }}>청산 {completedTrades.length}건 누적</span>
                  <span style={{ fontSize: 18, fontWeight: 700, color: pctColor(cumPct ?? 0) }}>
                    {cumPct != null ? pctStr(cumPct) : '-'}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <span style={{ fontSize: 9, color: '#6b7280' }}>{r.win_count}승 {r.lose_count}패</span>
                  <span style={{ fontSize: 9, color: '#6b7280' }}>적중 {r.win_rate.toFixed(0)}%</span>
                  <span style={{ fontSize: 9, color: '#6b7280' }}>평균 {pctStr(r.avg_return_pct)}</span>
                </div>
              </div>
            )}

            {cumPct != null && (
              <div>
                <div style={{ fontSize: 9, color: '#555', marginBottom: 5 }}>만약 이대로 투자했다면?</div>
                <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
                  <input value={inputAmt}
                    onChange={(e) => setInputAmt(e.target.value.replace(/[^0-9]/g, ''))}
                    style={{ ...inputStyle, flex: 1 }}
                    placeholder="투자금 입력" />
                  <span style={{ fontSize: 10, color: '#555', alignSelf: 'center' }}>원</span>
                </div>
                <div style={{ display: 'flex', gap: 3, marginBottom: 6 }}>
                  {[100, 500, 1000, 5000].map((w) => (
                    <button key={w} onClick={() => setInputAmt(String(w * 10000))}
                      style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, border: 'none', cursor: 'pointer', background: '#1e1e2e', color: '#888' }}>
                      {w}만
                    </button>
                  ))}
                </div>
                {principal > 0 && (
                  <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '7px 10px', background: '#0d0d1a', borderRadius: 5,
                    border: `1px solid ${pctColor(cumPct ?? 0)}33`,
                  }}>
                    <div>
                      <div style={{ fontSize: 9, color: '#555' }}>{fmtKRW(principal)}원 투자</div>
                      <div style={{ fontSize: 10, fontWeight: 600, color: pctColor(profit ?? 0), marginTop: 1 }}>
                        {profit != null ? `${profit >= 0 ? '+' : ''}${fmtKRW(Math.round(profit))}원` : '-'}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 9, color: '#555' }}>최종금액</div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: pctColor(cumPct ?? 0), marginTop: 1 }}>
                        {finalAmt != null ? `${fmtKRW(Math.round(finalAmt))}원` : '-'}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default WinRateSection;
