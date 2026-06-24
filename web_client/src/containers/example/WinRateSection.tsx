import React, { useState, useEffect } from 'react';
import { marketApi, WinRateResult, TradeRecord } from '../../api/stock';

interface Props {
  compact?: boolean;
  stockCode?: string;
}

const fmtKRW = (n: number) => {
  if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(1)}억`;
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(0)}만`;
  return n.toLocaleString();
};

const WinRateSection: React.FC<Props> = ({ compact, stockCode }) => {
  const [period, setPeriod] = useState('3m');
  const [holdDays, setHoldDays] = useState(5);
  const [results, setResults] = useState<WinRateResult[]>([]);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [inputAmt, setInputAmt] = useState('1000000');

  const fetchData = (p: string, hd: number, sc?: string) => {
    setLoading(true);
    marketApi.getWinRate({ stock_code: sc || undefined, period: p, hold_days: hd })
      .then((res) => {
        setResults(res.data.results);
        setTrades(res.data.trades || []);
      })
      .catch(() => { setResults([]); setTrades([]); })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (stockCode) fetchData(period, holdDays, stockCode);
  }, [stockCode]);

  const r = results[0] ?? null;
  const cumPct = r?.cumulative_return_pct ?? null;
  const cumColor = cumPct != null && cumPct >= 0 ? '#16a34a' : '#dc2626';

  const principal = parseFloat(inputAmt.replace(/,/g, '')) || 0;
  const finalAmt = cumPct != null && principal > 0 ? principal * (1 + cumPct / 100) : null;
  const profit = finalAmt != null ? finalAmt - principal : null;

  // 미실현 손익
  const unrealized = r?.unrealized_pct ?? null;

  const completedTrades = trades.filter((t) => t.return_pct != null);
  const openTrades = trades.filter((t) => t.unrealized_pct != null);

  if (compact) {
    return (
      <div>
        {/* 필터 */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 4, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 9, color: '#555', marginRight: 2 }}>분석기간</span>
          {(['1m', '3m', '6m', 'all'] as const).map((p) => (
            <button key={p}
              onClick={() => { setPeriod(p); fetchData(p, holdDays, stockCode); }}
              style={{
                padding: '2px 6px', fontSize: 10, borderRadius: 3, border: 'none', cursor: 'pointer',
                background: period === p ? '#6366f1' : '#1e1e2e',
                color: period === p ? '#fff' : '#888',
              }}>{p}</button>
          ))}
        </div>

        {loading && <div style={{ fontSize: 11, color: '#666' }}>불러오는 중...</div>}

        {!loading && (
          <>
            {/* 청산 수익률 */}
            {r && completedTrades.length > 0 && (
              <div style={{ textAlign: 'center', marginBottom: 8, padding: '8px 0', borderBottom: '1px solid #1e1e2e' }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: cumColor, lineHeight: 1 }}>
                  {cumPct != null ? `${cumPct >= 0 ? '+' : ''}${cumPct.toFixed(1)}%` : '-'}
                </div>
                <div style={{ fontSize: 9, color: '#4b5563', marginTop: 2 }}>
                  {period} 동안 매수→매도 신호 따랐을 때 누적 수익률
                </div>
                <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 4 }}>
                  <span style={{ fontSize: 9, color: '#6b7280' }}>{r.win_count}승 {r.lose_count}패</span>
                  <span style={{ fontSize: 9, color: '#6b7280' }}>적중 {r.win_rate.toFixed(0)}%</span>
                  <span style={{ fontSize: 9, color: r.avg_return_pct >= 0 ? '#16a34a' : '#dc2626' }}>
                    건당 평균 {r.avg_return_pct >= 0 ? '+' : ''}{r.avg_return_pct.toFixed(2)}%
                  </span>
                </div>
              </div>
            )}

            {/* 미실현 손익 */}
            {openTrades.length > 0 && (
              <div style={{
                background: '#0d0d1a', borderRadius: 6, padding: '6px 10px', marginBottom: 8,
                border: `1px solid ${(unrealized ?? 0) >= 0 ? '#16a34a33' : '#dc262633'}`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 9, color: '#555' }}>현재 보유 ({openTrades.length}건)</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: (unrealized ?? 0) >= 0 ? '#16a34a' : '#dc2626' }}>
                    미실현 {unrealized != null ? `${unrealized >= 0 ? '+' : ''}${unrealized.toFixed(2)}%` : '-'}
                  </span>
                </div>
                {openTrades.slice(0, 2).map((t, i) => (
                  <div key={i} style={{ fontSize: 9, color: '#555', marginTop: 2 }}>
                    {t.buy_date} 매수 → 현재 {t.unrealized_pct != null ? `${t.unrealized_pct >= 0 ? '+' : ''}${t.unrealized_pct.toFixed(2)}%` : '-'}
                  </div>
                ))}
              </div>
            )}

            {/* 데이터 없음 */}
            {!loading && completedTrades.length === 0 && openTrades.length === 0 && (
              <div style={{ fontSize: 10, color: '#555', textAlign: 'center', padding: '10px 0' }}>
                해당 기간 매수 신호 없음
              </div>
            )}

            {/* 시뮬레이션 */}
            {cumPct != null && (
              <>
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 9, color: '#555', marginBottom: 4 }}>투자금 시뮬레이션</div>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    <input value={inputAmt}
                      onChange={(e) => setInputAmt(e.target.value.replace(/[^0-9]/g, ''))}
                      style={{
                        flex: 1, background: '#1e1e2e', border: '1px solid #2d2d3d',
                        borderRadius: 4, padding: '4px 6px', fontSize: 10, color: '#e2e8f0', outline: 'none',
                      }}
                      placeholder="투자금 (원)" />
                    <span style={{ fontSize: 10, color: '#555', flexShrink: 0 }}>원</span>
                  </div>
                  <div style={{ display: 'flex', gap: 3, marginTop: 4 }}>
                    {[100, 500, 1000, 5000].map((w) => (
                      <button key={w} onClick={() => setInputAmt(String(w * 10000))}
                        style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, border: 'none', cursor: 'pointer', background: '#1e1e2e', color: '#888' }}>
                        {w}만
                      </button>
                    ))}
                  </div>
                </div>

                {principal > 0 && (
                  <div style={{ background: '#0d0d1a', borderRadius: 6, padding: '8px 10px', border: `1px solid ${cumColor}44` }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: 9, color: '#555' }}>투자원금</span>
                      <span style={{ fontSize: 10, color: '#9ca3af' }}>{fmtKRW(principal)}원</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: 9, color: '#555' }}>수익/손실</span>
                      <span style={{ fontSize: 10, fontWeight: 600, color: profit != null && profit >= 0 ? '#16a34a' : '#dc2626' }}>
                        {profit != null ? `${profit >= 0 ? '+' : ''}${fmtKRW(Math.round(profit))}원` : '-'}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 4, borderTop: '1px solid #1e1e2e' }}>
                      <span style={{ fontSize: 9, color: '#555' }}>최종금액</span>
                      <span style={{ fontSize: 12, color: cumColor, fontWeight: 700 }}>
                        {finalAmt != null ? `${fmtKRW(Math.round(finalAmt))}원` : '-'}
                      </span>
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    );
  }

  return null;
};

export default WinRateSection;
