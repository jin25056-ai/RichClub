import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { marketApi, PerformanceResponse, HoldingItem, TradeRecord } from '../api/stock';
import { useModel } from '../contexts/ModelContext';

const pctColor = (v: number) => v >= 0 ? '#16a34a' : '#dc2626';
const pctStr = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
const fmtKRW = (n: number) => {
  if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(1)}억`;
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(0)}만`;
  return n.toLocaleString();
};
const fmtPrice = (n: number) =>
  n >= 1000000 ? `${(n / 1000000).toFixed(1)}M`
  : n >= 1000 ? `${Math.round(n / 1000)}K`
  : String(n);

const PERIODS = ['1m', '3m', '6m', 'all'] as const;

const PerformancePage: React.FC = () => {
  const navigate = useNavigate();
  const { models, selectedModel, setSelectedModel } = useModel();
  const [data, setData] = useState<PerformanceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState<string>('3m');
  const [inputAmt, setInputAmt] = useState('10000000');
  const [activeTab, setActiveTab] = useState<'holdings' | 'trades'>('holdings');

  const fetchData = (modelId: string, p: string) => {
    setLoading(true);
    marketApi.getPerformance(modelId, p)
      .then((res) => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!localStorage.getItem('access_token')) { navigate('/auth'); return; }
    fetchData(selectedModel, period);
  }, [selectedModel, period]);

  const principal = parseFloat(inputAmt.replace(/,/g, '')) || 0;
  const finalAmt = data && principal > 0 ? principal * (1 + data.cumulative_return_pct / 100) : null;
  const profit = finalAmt != null ? finalAmt - principal : null;
  const completedTrades = data?.trades.filter((t) => t.return_pct != null) ?? [];

  return (
    <div style={{ background: '#0a0a14', minHeight: '100vh', fontFamily: 'inherit', color: '#e2e8f0' }}>
      {/* 헤더 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 20px', borderBottom: '1px solid #1e1e2e' }}>
        <button onClick={() => navigate(-1)}
          style={{ background: 'none', border: 'none', color: '#6b7280', fontSize: 18, cursor: 'pointer', lineHeight: 1, padding: '0 4px' }}>
          &#8592;
        </button>
        <span style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0' }}>AI 실적</span>
        <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
          {models.map((m) => (
            <button key={m.id} onClick={() => { if (m.available) setSelectedModel(m.id); }}
              disabled={!m.available}
              style={{
                padding: '3px 10px', fontSize: 10, borderRadius: 4, border: 'none', cursor: m.available ? 'pointer' : 'default',
                background: selectedModel === m.id ? '#6366f1' : '#1e1e2e',
                color: selectedModel === m.id ? '#fff' : m.available ? '#9ca3af' : '#374151',
              }}>
              {m.name}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>
          {PERIODS.map((p) => (
            <button key={p} onClick={() => setPeriod(p)}
              style={{ padding: '3px 8px', fontSize: 10, borderRadius: 4, border: 'none', cursor: 'pointer', background: period === p ? '#6366f1' : '#1e1e2e', color: period === p ? '#fff' : '#555' }}>
              {p}
            </button>
          ))}
        </div>
      </div>

      <div style={{ padding: '16px 20px', maxWidth: 1000, margin: '0 auto' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#4b5563' }}>불러오는 중...</div>
        ) : !data ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#4b5563' }}>데이터 없음</div>
        ) : (
          <>
            {/* 핵심 지표 */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 16 }}>
              <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, padding: '16px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#4b5563', marginBottom: 6 }}>승률</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: data.win_rate >= 50 ? '#16a34a' : '#dc2626' }}>
                  {data.win_rate.toFixed(1)}%
                </div>
                <div style={{ fontSize: 10, color: '#374151', marginTop: 4 }}>{data.win_count}승 {data.lose_count}패</div>
              </div>
              <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, padding: '16px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#4b5563', marginBottom: 6 }}>누적 수익률</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: pctColor(data.cumulative_return_pct) }}>
                  {pctStr(data.cumulative_return_pct)}
                </div>
                <div style={{ fontSize: 10, color: '#374151', marginTop: 4 }}>평균 {pctStr(data.avg_return_pct)}</div>
              </div>
              <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, padding: '16px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#4b5563', marginBottom: 6 }}>거래 횟수</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: '#a5b4fc' }}>{data.total_trades}건</div>
                <div style={{ fontSize: 10, color: '#374151', marginTop: 4 }}>
                  최고 {pctStr(data.max_return_pct)} / 최저 {pctStr(data.max_loss_pct)}
                </div>
              </div>
            </div>

            {/* 투자금 시뮬레이션 */}
            <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, padding: '16px 20px', marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', marginBottom: 12 }}>투자금 시뮬레이션</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <input value={inputAmt}
                  onChange={(e) => setInputAmt(e.target.value.replace(/[^0-9]/g, ''))}
                  style={{ flex: 1, background: '#1e1e2e', border: '1px solid #2d2d3d', borderRadius: 6, padding: '6px 10px', fontSize: 12, color: '#e2e8f0', outline: 'none' }}
                  placeholder="투자금 입력" />
                <span style={{ fontSize: 11, color: '#555' }}>원</span>
                {[['100만', 1000000], ['500만', 5000000], ['1000만', 10000000], ['5000만', 50000000]].map(([label, val]) => (
                  <button key={label as string} onClick={() => setInputAmt(String(val))}
                    style={{ fontSize: 10, padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', background: '#1e1e2e', color: '#888', flexShrink: 0 }}>
                    {label}
                  </button>
                ))}
              </div>
              {principal > 0 && finalAmt != null && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#0d0d1a', borderRadius: 8, border: `1px solid ${pctColor(data.cumulative_return_pct)}33` }}>
                  <div>
                    <div style={{ fontSize: 11, color: '#555', marginBottom: 4 }}>{fmtKRW(principal)}원 투자 시</div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: pctColor(profit ?? 0) }}>
                      {profit != null ? `${profit >= 0 ? '+' : ''}${fmtKRW(Math.round(profit))}원` : '-'}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: '#555', marginBottom: 4 }}>최종금액</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: pctColor(data.cumulative_return_pct) }}>
                      {fmtKRW(Math.round(finalAmt))}원
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 탭: 보유종목 / 매매기록 */}
            <div style={{ display: 'flex', gap: 0, marginBottom: 12, borderBottom: '1px solid #1e1e2e' }}>
              {[['holdings', `현재 보유 종목 (${data.holdings.length})`], ['trades', `매매 기록 (${completedTrades.length}건)`]].map(([key, label]) => (
                <button key={key} onClick={() => setActiveTab(key as 'holdings' | 'trades')}
                  style={{
                    padding: '8px 16px', fontSize: 11, border: 'none', cursor: 'pointer',
                    background: 'transparent',
                    color: activeTab === key ? '#a5b4fc' : '#555',
                    fontWeight: activeTab === key ? 600 : 400,
                    borderBottom: activeTab === key ? '2px solid #6366f1' : '2px solid transparent',
                  }}>
                  {label}
                </button>
              ))}
            </div>

            {/* 보유 종목 */}
            {activeTab === 'holdings' && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 8 }}>
                {data.holdings.length === 0 ? (
                  <div style={{ color: '#4b5563', fontSize: 12, padding: '20px 0' }}>현재 보유 종목 없음</div>
                ) : data.holdings.map((h: HoldingItem) => (
                  <div key={h.stock_code}
                    onClick={() => navigate(`/?code=${h.stock_code}`)}
                    style={{
                      background: '#0f0f1a', border: `1px solid ${pctColor(h.unrealized_pct)}22`,
                      borderRadius: 8, padding: '12px 14px', cursor: 'pointer',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = '#1a1a30')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = '#0f0f1a')}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 600, color: '#d1d5db', marginBottom: 2 }}>{h.stock_name}</div>
                        <div style={{ fontSize: 9, color: '#4b5563' }}>{h.stock_code}</div>
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: pctColor(h.unrealized_pct) }}>
                        {pctStr(h.unrealized_pct)}
                      </div>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#6b7280' }}>
                      <span>매수 {h.buy_date} · {fmtPrice(h.buy_price)}</span>
                      <span>현재 {fmtPrice(h.current_price)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 매매 기록 */}
            {activeTab === 'trades' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {completedTrades.length === 0 ? (
                  <div style={{ color: '#4b5563', fontSize: 12, padding: '20px 0' }}>매매 기록 없음</div>
                ) : completedTrades.map((t: TradeRecord, i: number) => (
                  <div key={i}
                    onClick={() => { if (t.stock_code) navigate(`/?code=${t.stock_code}`); }}
                    style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '10px 14px', borderRadius: 8, cursor: t.stock_code ? 'pointer' : 'default',
                      background: (t.return_pct ?? 0) >= 0 ? '#14532d12' : '#7f1d1d12',
                      border: `1px solid ${pctColor(t.return_pct ?? 0)}22`,
                    }}
                    onMouseEnter={(e) => { if (t.stock_code) e.currentTarget.style.opacity = '0.8'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                  >
                    <div>
                      <div style={{ fontSize: 12, color: '#d1d5db', fontWeight: 500, marginBottom: 4 }}>
                        {t.stock_name}
                        <span style={{ fontSize: 9, color: '#4b5563', marginLeft: 6 }}>{t.stock_code}</span>
                      </div>
                      <div style={{ display: 'flex', gap: 8, fontSize: 10, color: '#6b7280' }}>
                        <span><span style={{ color: '#16a34a', fontWeight: 600 }}>B</span> {t.buy_date} · {fmtPrice(t.buy_price)}</span>
                        <span style={{ color: '#374151' }}>→</span>
                        <span><span style={{ color: '#dc2626', fontWeight: 600 }}>S</span> {t.sell_date} · {fmtPrice(t.sell_price ?? 0)}</span>
                      </div>
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: pctColor(t.return_pct ?? 0), flexShrink: 0, marginLeft: 16 }}>
                      {pctStr(t.return_pct ?? 0)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default PerformancePage;
