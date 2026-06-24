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
}

const WinRateSection: React.FC<Props> = ({ compact }) => {
  const [period, setPeriod] = useState('3m');
  const [holdDays, setHoldDays] = useState(5);
  const [results, setResults] = useState<WinRateResult[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = (p: string, hd: number) => {
    setLoading(true);
    marketApi.getWinRate({ period: p, hold_days: hd })
      .then((res) => setResults(res.data.results))
      .catch(() => setResults([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData('3m', 5); }, []);

  // 전체 누적 수익률: 서버값 있으면 복리 합산, 없으면 평균수익 단순 합산
  const totalCumPct = results.length > 0
    ? results.reduce((acc, r) => {
        const cum = r.cumulative_return_pct;
        if (cum != null) return acc * (1 + cum / 100);
        return acc;
      }, 1.0)
    : null;
  const totalPct = totalCumPct != null ? (totalCumPct - 1) * 100 : null;
  const totalColor = totalPct != null && totalPct >= 0 ? '#16a34a' : '#dc2626';

  if (compact) {
    return (
      <div>
        {/* 필터 */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {(['1m', '3m', '6m', 'all'] as const).map((p) => (
            <button key={p}
              onClick={() => { setPeriod(p); fetchData(p, holdDays); }}
              style={{
                padding: '2px 6px', fontSize: 10, borderRadius: 3, border: 'none', cursor: 'pointer',
                background: period === p ? '#6366f1' : '#1e1e2e',
                color: period === p ? '#fff' : '#888',
              }}>{p}</button>
          ))}
          <select value={holdDays}
            onChange={(e) => { setHoldDays(Number(e.target.value)); fetchData(period, Number(e.target.value)); }}
            style={{ fontSize: 10, background: '#1e1e2e', color: '#888', border: 'none', borderRadius: 3, padding: '2px 4px' }}>
            {[1, 3, 5, 10, 20].map((d) => <option key={d} value={d}>{d}일</option>)}
          </select>
        </div>

        {loading && <div style={{ fontSize: 11, color: '#666' }}>불러오는 중...</div>}

        {!loading && results.length > 0 && (
          <>
            {/* 전체 합산 누적 수익률 크게 */}
            <div style={{
              textAlign: 'center', marginBottom: 10,
              padding: '10px 0', borderBottom: '1px solid #1e1e2e',
            }}>
              {totalPct != null ? (
                <>
                  <div style={{ fontSize: 24, fontWeight: 700, color: totalColor, lineHeight: 1 }}>
                    {totalPct >= 0 ? '+' : ''}{totalPct.toFixed(1)}%
                  </div>
                  <div style={{ fontSize: 9, color: '#4b5563', marginTop: 3 }}>
                    {period} 동안 신호 전부 따랐을 때 누적 수익률
                  </div>
                </>
              ) : (
                <div style={{ fontSize: 9, color: '#555' }}>집계 중...</div>
              )}
            </div>

            {/* 신호별 소형 요약 */}
            {results.map((r) => (
              <div key={r.signal} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '5px 2px', borderBottom: '1px solid #13131e',
              }}>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 3,
                  background: SIGNAL_BG[r.signal], color: SIGNAL_COLOR[r.signal], flexShrink: 0,
                }}>{r.signal}</span>
                <span style={{ fontSize: 10, color: '#6b7280' }}>
                  적중 {r.win_rate.toFixed(0)}%
                </span>
                <span style={{
                  fontSize: 10, fontWeight: 600,
                  color: r.avg_return_pct >= 0 ? '#16a34a' : '#dc2626',
                }}>
                  {r.avg_return_pct >= 0 ? '+' : ''}{r.avg_return_pct.toFixed(2)}%
                </span>
                <span style={{ fontSize: 9, color: '#555' }}>{r.total_signals}건</span>
              </div>
            ))}
          </>
        )}
      </div>
    );
  }

  return null;
};

export default WinRateSection;
