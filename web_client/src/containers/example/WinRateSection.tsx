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
          <div>
            {results.map((r) => {
              // 누적 수익률: 서버에서 오면 사용, 없으면 avg * total 로 단순 추정
              const cumPct = r.cumulative_return_pct ?? r.avg_return_pct * r.total_signals;
              const cumColor = cumPct >= 0 ? '#16a34a' : '#dc2626';
              return (
                <div key={r.signal} style={{
                  background: '#0d0d1a', border: `1px solid ${SIGNAL_COLOR[r.signal]}33`,
                  borderRadius: 6, padding: '8px 10px', marginBottom: 6,
                }}>
                  {/* 헤더 */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{
                      fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 3,
                      background: SIGNAL_BG[r.signal], color: SIGNAL_COLOR[r.signal],
                    }}>{r.signal}</span>
                    <span style={{ fontSize: 9, color: '#555' }}>{r.total_signals}건 · {holdDays}일</span>
                  </div>

                  {/* 누적 수익률 - 가장 크게 */}
                  <div style={{ textAlign: 'center', marginBottom: 8 }}>
                    <div style={{ fontSize: 22, fontWeight: 700, color: cumColor, lineHeight: 1 }}>
                      {cumPct >= 0 ? '+' : ''}{cumPct.toFixed(1)}%
                    </div>
                    <div style={{ fontSize: 9, color: '#4b5563', marginTop: 2 }}>
                      신호 그대로 따랐을 때 {period} 누적 수익률
                    </div>
                  </div>

                  {/* 적중률 + 평균 수익 */}
                  <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                    <div style={{ flex: 1, textAlign: 'center', background: '#0a0a14', borderRadius: 4, padding: '4px 0' }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: SIGNAL_COLOR[r.signal] }}>
                        {r.win_rate.toFixed(0)}%
                      </div>
                      <div style={{ fontSize: 9, color: '#555' }}>적중률</div>
                    </div>
                    <div style={{ flex: 1, textAlign: 'center', background: '#0a0a14', borderRadius: 4, padding: '4px 0' }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: r.avg_return_pct >= 0 ? '#16a34a' : '#dc2626' }}>
                        {r.avg_return_pct >= 0 ? '+' : ''}{r.avg_return_pct.toFixed(2)}%
                      </div>
                      <div style={{ fontSize: 9, color: '#555' }}>건당 평균</div>
                    </div>
                  </div>

                  {/* 최대 수익/손실 */}
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 9, color: '#16a34a' }}>
                      최대 +{(r.max_return_pct ?? 0).toFixed(1)}%
                    </span>
                    <span style={{ fontSize: 9, color: '#6b7280' }}>
                      {r.win_count}승 {r.lose_count}패
                    </span>
                    <span style={{ fontSize: 9, color: '#dc2626' }}>
                      최대 {(r.max_loss_pct ?? 0).toFixed(1)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return null;
};

export default WinRateSection;
