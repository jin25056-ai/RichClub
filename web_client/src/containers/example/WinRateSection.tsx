import React, { useState, useEffect } from 'react';
import { marketApi, WinRateResult } from '../../api/stock';

const SIGNAL_COLOR: Record<string, string> = {
  매수: '#16a34a', 매도: '#dc2626', 관망: '#d97706',
};
const SIGNAL_BG: Record<string, string> = {
  매수: '#14532d', 매도: '#7f1d1d', 관망: '#78350f',
};

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
  const [loading, setLoading] = useState(false);
  const [inputAmt, setInputAmt] = useState('1000000');

  const fetchData = (p: string, hd: number, sc?: string) => {
    setLoading(true);
    marketApi.getWinRate({ stock_code: sc || undefined, period: p, hold_days: hd })
      .then((res) => setResults(res.data.results))
      .catch(() => setResults([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(period, holdDays, stockCode);
  }, [stockCode]);

  const totalCumPct = results.length > 0 && results.every((r) => r.cumulative_return_pct != null)
    ? results.reduce((acc, r) => acc * (1 + (r.cumulative_return_pct ?? 0) / 100), 1.0)
    : null;
  const totalPct = totalCumPct != null ? (totalCumPct - 1) * 100 : null;
  const totalColor = totalPct != null && totalPct >= 0 ? '#16a34a' : '#dc2626';

  const principal = parseFloat(inputAmt.replace(/,/g, '')) || 0;
  const finalAmt = totalCumPct != null && principal > 0 ? principal * totalCumPct : null;
  const profit = finalAmt != null ? finalAmt - principal : null;

  if (compact) {
    return (
      <div>
        {/* 필터 */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {(['1m', '3m', '6m', 'all'] as const).map((p) => (
            <button key={p}
              onClick={() => { setPeriod(p); fetchData(p, holdDays, stockCode); }}
              style={{
                padding: '2px 6px', fontSize: 10, borderRadius: 3, border: 'none', cursor: 'pointer',
                background: period === p ? '#6366f1' : '#1e1e2e',
                color: period === p ? '#fff' : '#888',
              }}>{p}</button>
          ))}
          <select value={holdDays}
            onChange={(e) => { setHoldDays(Number(e.target.value)); fetchData(period, Number(e.target.value), stockCode); }}
            style={{ fontSize: 10, background: '#1e1e2e', color: '#888', border: 'none', borderRadius: 3, padding: '2px 4px' }}>
            {[1, 3, 5, 10, 20].map((d) => <option key={d} value={d}>{d}일</option>)}
          </select>
        </div>

        {loading && <div style={{ fontSize: 11, color: '#666' }}>불러오는 중...</div>}

        {!loading && results.length > 0 && (
          <>
            {/* 전체 누적 수익률 */}
            <div style={{ textAlign: 'center', marginBottom: 8, padding: '8px 0', borderBottom: '1px solid #1e1e2e' }}>
              {totalPct != null ? (
                <>
                  <div style={{ fontSize: 22, fontWeight: 700, color: totalColor, lineHeight: 1 }}>
                    {totalPct >= 0 ? '+' : ''}{totalPct.toFixed(1)}%
                  </div>
                  <div style={{ fontSize: 9, color: '#4b5563', marginTop: 2 }}>
                    {period} 동안 신호 전부 따랐을 때 누적 수익률
                  </div>
                </>
              ) : (
                <div style={{ fontSize: 9, color: '#555' }}>배포 후 정확한 값 표시</div>
              )}
            </div>

            {/* 시뮬레이션 인풋 */}
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 9, color: '#555', marginBottom: 4 }}>투자금 시뮬레이션</div>
              <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                <input
                  value={inputAmt}
                  onChange={(e) => setInputAmt(e.target.value.replace(/[^0-9]/g, ''))}
                  style={{
                    flex: 1, background: '#1e1e2e', border: '1px solid #2d2d3d',
                    borderRadius: 4, padding: '4px 6px', fontSize: 10, color: '#e2e8f0', outline: 'none',
                  }}
                  placeholder="투자금 (원)"
                />
                <span style={{ fontSize: 10, color: '#555', flexShrink: 0 }}>원</span>
              </div>
              <div style={{ display: 'flex', gap: 3, marginTop: 4, flexWrap: 'wrap' }}>
                {[100, 500, 1000, 5000].map((w) => (
                  <button key={w} onClick={() => setInputAmt(String(w * 10000))}
                    style={{
                      fontSize: 9, padding: '1px 5px', borderRadius: 3, border: 'none',
                      cursor: 'pointer', background: '#1e1e2e', color: '#888',
                    }}>{w}만</button>
                ))}
              </div>
            </div>

            {/* 시뮬레이션 결과 */}
            {principal > 0 && (
              <div style={{
                background: '#0d0d1a', borderRadius: 6, padding: '8px 10px', marginBottom: 8,
                border: `1px solid ${totalColor}44`,
              }}>
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
                  <span style={{ fontSize: 12, color: totalColor, fontWeight: 700 }}>
                    {finalAmt != null ? `${fmtKRW(Math.round(finalAmt))}원` : '-'}
                  </span>
                </div>
              </div>
            )}

            {/* 신호별 요약 */}
            {results.map((r) => (
              <div key={r.signal} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '4px 2px', borderBottom: '1px solid #13131e',
              }}>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 3,
                  background: SIGNAL_BG[r.signal], color: SIGNAL_COLOR[r.signal], flexShrink: 0,
                }}>{r.signal}</span>
                <span style={{ fontSize: 10, color: '#6b7280' }}>
                  적중 {r.win_rate.toFixed(0)}%
                </span>
                <span style={{ fontSize: 10, fontWeight: 600, color: r.avg_return_pct >= 0 ? '#16a34a' : '#dc2626' }}>
                  {r.avg_return_pct >= 0 ? '+' : ''}{r.avg_return_pct.toFixed(2)}%
                </span>
                <span style={{ fontSize: 9, color: '#555' }}>{r.total_signals}건</span>
              </div>
            ))}
          </>
        )}

        {!loading && results.length === 0 && (
          <div style={{ fontSize: 10, color: '#555', textAlign: 'center', padding: '10px 0' }}>
            해당 종목 데이터 없음
          </div>
        )}
      </div>
    );
  }

  return null;
};

export default WinRateSection;
