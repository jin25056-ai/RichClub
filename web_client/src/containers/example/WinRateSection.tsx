import React, { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import { marketApi, WinRateResult } from '../../api/stock';

const SIGNAL_COLOR: Record<string, string> = {
  매수: '#16a34a', 매도: '#dc2626', 관망: '#d97706',
};

interface Props {
  compact?: boolean;
}

const WinRateSection: React.FC<Props> = ({ compact }) => {
  const [stockCode, setStockCode] = useState('');
  const [period, setPeriod] = useState('3m');
  const [holdDays, setHoldDays] = useState(5);
  const [results, setResults] = useState<WinRateResult[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = (sc: string, p: string, hd: number) => {
    setLoading(true);
    marketApi.getWinRate({ stock_code: sc || undefined, period: p, hold_days: hd })
      .then((res) => setResults(res.data.results))
      .catch(() => setResults([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData('', '3m', 5); }, []);

  const chartData = results.map((r) => ({
    name: r.signal, 승률: r.win_rate, 평균수익률: r.avg_return_pct,
  }));

  if (compact) {
    return (
      <div>
        {/* 필터 */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'wrap' }}>
          {(['1m', '3m', '6m', 'all'] as const).map((p) => (
            <button key={p}
              onClick={() => { setPeriod(p); fetchData(stockCode, p, holdDays); }}
              style={{
                padding: '2px 6px', fontSize: 10, borderRadius: 3, border: 'none', cursor: 'pointer',
                background: period === p ? '#6366f1' : '#1e1e2e', color: period === p ? '#fff' : '#888',
              }}>{p}</button>
          ))}
          <select value={holdDays}
            onChange={(e) => { setHoldDays(Number(e.target.value)); fetchData(stockCode, period, Number(e.target.value)); }}
            style={{ fontSize: 10, background: '#1e1e2e', color: '#888', border: 'none', borderRadius: 3, padding: '2px 4px' }}>
            {[1, 3, 5, 10, 20].map((d) => <option key={d} value={d}>{d}일</option>)}
          </select>
        </div>

        {loading && <div style={{ fontSize: 11, color: '#666' }}>불러오는 중...</div>}

        {!loading && results.length > 0 && (
          <>
            {results.map((r) => (
              <div key={r.signal} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '5px 0', borderBottom: '1px solid #13131e',
              }}>
                <span style={{ fontSize: 11, color: SIGNAL_COLOR[r.signal], fontWeight: 600 }}>{r.signal}</span>
                <span style={{ fontSize: 11, color: '#d1d5db' }}>{r.win_rate.toFixed(1)}%</span>
                <span style={{ fontSize: 11, color: r.avg_return_pct >= 0 ? '#16a34a' : '#dc2626' }}>
                  {r.avg_return_pct >= 0 ? '+' : ''}{r.avg_return_pct.toFixed(2)}%
                </span>
                <span style={{ fontSize: 10, color: '#555' }}>{r.total_signals}건</span>
              </div>
            ))}
            <div style={{ marginTop: 10 }}>
              <ResponsiveContainer width="100%" height={100}>
                <BarChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#888' }} />
                  <YAxis tick={{ fontSize: 9, fill: '#666' }} />
                  <Tooltip contentStyle={{ background: '#1e1e2e', border: '1px solid #333', fontSize: 11 }} />
                  <Bar dataKey="승률">
                    {chartData.map((entry) => (
                      <Cell key={entry.name} fill={SIGNAL_COLOR[entry.name] ?? '#6366f1'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </div>
    );
  }

  // 기본 레이아웃
  return (
    <div>
      <div className="ex-filter-row" style={{ flexWrap: 'wrap', gap: 8 }}>
        <input className="ex-input" placeholder="종목코드 (비워두면 전체)" value={stockCode}
          onChange={(e) => setStockCode(e.target.value)} style={{ width: 160 }} />
        {(['1m', '3m', '6m', 'all'] as const).map((p) => (
          <button key={p} className={`ex-filter-btn${period === p ? ' active' : ''}`}
            onClick={() => { setPeriod(p); fetchData(stockCode, p, holdDays); }}>{p}</button>
        ))}
        <select className="ex-input" value={holdDays}
          onChange={(e) => { setHoldDays(Number(e.target.value)); fetchData(stockCode, period, Number(e.target.value)); }}
          style={{ width: 110 }}>
          {[1, 3, 5, 10, 20].map((d) => <option key={d} value={d}>{d}일 보유</option>)}
        </select>
        <button className="ex-btn" onClick={() => fetchData(stockCode, period, holdDays)}>조회</button>
      </div>
      {loading && <div className="ex-loading">불러오는 중...</div>}
      {!loading && results.length > 0 && (
        <>
          <div className="ex-market-grid" style={{ marginBottom: 24 }}>
            {results.map((r) => (
              <div key={r.signal} className="ex-market-card">
                <span className="ex-badge" style={{ background: SIGNAL_COLOR[r.signal] }}>{r.signal}</span>
                <div style={{ marginTop: 8, fontSize: 22, fontWeight: 700, color: '#fff' }}>{r.win_rate.toFixed(1)}%</div>
                <div style={{ fontSize: 12, color: '#aaa' }}>승률</div>
                <div style={{ marginTop: 4, color: r.avg_return_pct >= 0 ? '#16a34a' : '#dc2626' }}>
                  평균 {r.avg_return_pct >= 0 ? '+' : ''}{r.avg_return_pct.toFixed(2)}%
                </div>
                <div style={{ fontSize: 11, color: '#888', marginTop: 4 }}>
                  {r.win_count}승 / {r.lose_count}패 ({r.total_signals}건)
                </div>
              </div>
            ))}
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="name" tick={{ fill: '#aaa' }} />
              <YAxis tick={{ fill: '#aaa' }} />
              <Tooltip contentStyle={{ background: '#1e1e2e', border: '1px solid #333', color: '#fff' }} />
              <Bar dataKey="승률">
                {chartData.map((entry) => <Cell key={entry.name} fill={SIGNAL_COLOR[entry.name] ?? '#6366f1'} />)}
              </Bar>
              <Bar dataKey="평균수익률" fill="#6366f1" />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  );
};

export default WinRateSection;
