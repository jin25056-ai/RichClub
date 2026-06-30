import React, { useState, useEffect } from 'react';
import { marketApi, PerformanceResponse, HoldingItem, TradeRecord } from '../../api/stock';

interface Props {
  modelId: string;
  onSelectStock?: (code: string, name: string) => void;
}

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

const PerformanceSection: React.FC<Props> = ({ modelId, onSelectStock }) => {
  const [data, setData] = useState<PerformanceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState<string>('3m');
  const [showDetail, setShowDetail] = useState(false);
  const [inputAmt, setInputAmt] = useState('10000000');

  const fetch = (p: string) => {
    setLoading(true);
    marketApi.getPerformance(modelId, p)
      .then((res) => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetch(period); }, [modelId, period]);

  const principal = parseFloat(inputAmt.replace(/,/g, '')) || 0;
  const finalAmt = data && principal > 0
    ? principal * (1 + data.cumulative_return_pct / 100)
    : null;
  const profit = finalAmt != null ? finalAmt - principal : null;

  const completedTrades = data?.trades.filter((t) => t.return_pct != null) ?? [];

  return (
    <div style={{ marginBottom: 10 }}>
      {/* 상단 요약 배너 */}
      <div style={{
        background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8,
        padding: '10px 14px', marginBottom: 6,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: '#a5b4fc' }}>AI 실적</span>
            <span style={{ fontSize: 9, color: '#4b5563' }}>{modelId}</span>
          </div>
          <div style={{ display: 'flex', gap: 3 }}>
            {PERIODS.map((p) => (
              <button key={p} onClick={() => setPeriod(p)}
                style={{
                  padding: '2px 6px', fontSize: 9, borderRadius: 3, border: 'none', cursor: 'pointer',
                  background: period === p ? '#6366f1' : '#1e1e2e',
                  color: period === p ? '#fff' : '#555',
                }}>
                {p}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div style={{ fontSize: 10, color: '#4b5563', textAlign: 'center', padding: '8px 0' }}>불러오는 중...</div>
        ) : data ? (
          <>
            {/* 핵심 지표 3개 */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
              <div style={{ flex: 1, background: '#13131e', borderRadius: 6, padding: '8px 10px', textAlign: 'center' }}>
                <div style={{ fontSize: 9, color: '#4b5563', marginBottom: 3 }}>승률</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: data.win_rate >= 50 ? '#16a34a' : '#dc2626' }}>
                  {data.win_rate.toFixed(1)}%
                </div>
                <div style={{ fontSize: 8, color: '#374151' }}>{data.win_count}승 {data.lose_count}패</div>
              </div>
              <div style={{ flex: 1, background: '#13131e', borderRadius: 6, padding: '8px 10px', textAlign: 'center' }}>
                <div style={{ fontSize: 9, color: '#4b5563', marginBottom: 3 }}>누적수익률</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: pctColor(data.cumulative_return_pct) }}>
                  {pctStr(data.cumulative_return_pct)}
                </div>
                <div style={{ fontSize: 8, color: '#374151' }}>평균 {pctStr(data.avg_return_pct)}</div>
              </div>
              <div style={{ flex: 1, background: '#13131e', borderRadius: 6, padding: '8px 10px', textAlign: 'center' }}>
                <div style={{ fontSize: 9, color: '#4b5563', marginBottom: 3 }}>거래횟수</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#a5b4fc' }}>{data.total_trades}</div>
                <div style={{ fontSize: 8, color: '#374151' }}>최고 {pctStr(data.max_return_pct)}</div>
              </div>
            </div>

            {/* 투자금 시뮬레이션 */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', gap: 4, marginBottom: 4, alignItems: 'center' }}>
                <input value={inputAmt}
                  onChange={(e) => setInputAmt(e.target.value.replace(/[^0-9]/g, ''))}
                  style={{
                    flex: 1, background: '#1e1e2e', border: '1px solid #2d2d3d',
                    borderRadius: 4, padding: '3px 6px', fontSize: 10,
                    color: '#e2e8f0', outline: 'none',
                  }}
                  placeholder="투자금 입력" />
                <span style={{ fontSize: 9, color: '#555' }}>원</span>
              </div>
              <div style={{ display: 'flex', gap: 3, marginBottom: 6 }}>
                {[[100, '100만'], [500, '500만'], [1000, '1000만'], [5000, '5000만']].map(([w, label]) => (
                  <button key={w} onClick={() => setInputAmt(String(Number(w) * 10000))}
                    style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, border: 'none', cursor: 'pointer', background: '#1e1e2e', color: '#888' }}>
                    {label}
                  </button>
                ))}
              </div>
              {principal > 0 && finalAmt != null && (
                <div style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '7px 10px', background: '#0d0d1a', borderRadius: 5,
                  border: `1px solid ${pctColor(data.cumulative_return_pct)}33`,
                }}>
                  <div>
                    <div style={{ fontSize: 9, color: '#555' }}>{fmtKRW(principal)}원 투자</div>
                    <div style={{ fontSize: 10, fontWeight: 600, color: pctColor(profit ?? 0), marginTop: 1 }}>
                      {profit != null ? `${profit >= 0 ? '+' : ''}${fmtKRW(Math.round(profit))}원` : '-'}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 9, color: '#555' }}>최종금액</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: pctColor(data.cumulative_return_pct) }}>
                      {fmtKRW(Math.round(finalAmt))}원
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 현재 보유 종목 */}
            {data.holdings.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 9, color: '#4b5563', marginBottom: 5 }}>현재 보유 종목 ({data.holdings.length})</div>
                {data.holdings.map((h: HoldingItem) => (
                  <div key={h.stock_code}
                    onClick={() => onSelectStock?.(h.stock_code, h.stock_name)}
                    style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '5px 8px', marginBottom: 2, borderRadius: 5, cursor: 'pointer',
                      background: '#13131e', border: `1px solid ${pctColor(h.unrealized_pct)}22`,
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = '#1a1a30')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = '#13131e')}
                  >
                    <div>
                      <div style={{ fontSize: 10, color: '#d1d5db', fontWeight: 500 }}>{h.stock_name}</div>
                      <div style={{ fontSize: 8, color: '#4b5563' }}>
                        {h.buy_date} 매수 · {fmtPrice(h.buy_price)}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: pctColor(h.unrealized_pct) }}>
                        {pctStr(h.unrealized_pct)}
                      </div>
                      <div style={{ fontSize: 8, color: '#4b5563' }}>{fmtPrice(h.current_price)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 상세보기 버튼 */}
            <button onClick={() => setShowDetail(true)}
              style={{
                width: '100%', padding: '6px 0', fontSize: 10, borderRadius: 5,
                border: '1px solid #2d2d3d', background: 'transparent',
                color: '#6b7280', cursor: 'pointer',
              }}>
              AI 실적 상세보기 ({completedTrades.length}건)
            </button>
          </>
        ) : (
          <div style={{ fontSize: 10, color: '#4b5563', textAlign: 'center', padding: '8px 0' }}>
            데이터 없음
          </div>
        )}
      </div>

      {/* 상세보기 모달 */}
      {showDetail && data && (
        <div onClick={() => setShowDetail(false)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
            zIndex: 3000, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
          <div onClick={(e) => e.stopPropagation()}
            style={{
              background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10,
              padding: '20px', width: '90vw', maxWidth: 600, maxHeight: '80vh',
              display: 'flex', flexDirection: 'column',
            }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <span style={{ fontSize: 13, fontWeight: 700, color: '#e2e8f0' }}>AI 매매 기록</span>
                <span style={{ fontSize: 10, color: '#4b5563', marginLeft: 8 }}>{modelId} · {period}</span>
              </div>
              <button onClick={() => setShowDetail(false)}
                style={{ background: 'none', border: 'none', color: '#6b7280', fontSize: 18, cursor: 'pointer', lineHeight: 1 }}>
                &#x2715;
              </button>
            </div>

            {/* 요약 */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
              {[
                ['승률', `${data.win_rate.toFixed(1)}%`, data.win_rate >= 50 ? '#16a34a' : '#dc2626'],
                ['누적수익', pctStr(data.cumulative_return_pct), pctColor(data.cumulative_return_pct)],
                ['거래', `${data.total_trades}건`, '#a5b4fc'],
                ['최고', pctStr(data.max_return_pct), '#16a34a'],
                ['최저', pctStr(data.max_loss_pct), '#dc2626'],
              ].map(([label, value, color]) => (
                <div key={label} style={{ flex: 1, background: '#13131e', borderRadius: 6, padding: '6px 8px', textAlign: 'center' }}>
                  <div style={{ fontSize: 8, color: '#4b5563', marginBottom: 2 }}>{label}</div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: color as string }}>{value}</div>
                </div>
              ))}
            </div>

            {/* 매매 기록 */}
            <div style={{ overflowY: 'auto', flex: 1 }}>
              {completedTrades.map((t: TradeRecord, i: number) => (
                <div key={i}
                  onClick={() => { if (t.stock_code && t.stock_name) { onSelectStock?.(t.stock_code, t.stock_name); setShowDetail(false); } }}
                  style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '8px 10px', marginBottom: 3, borderRadius: 6, cursor: t.stock_code ? 'pointer' : 'default',
                    background: (t.return_pct ?? 0) >= 0 ? '#14532d18' : '#7f1d1d18',
                    border: `1px solid ${pctColor(t.return_pct ?? 0)}22`,
                  }}
                  onMouseEnter={(e) => { if (t.stock_code) e.currentTarget.style.opacity = '0.8'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                >
                  <div>
                    <div style={{ fontSize: 11, color: '#d1d5db', fontWeight: 500, marginBottom: 3 }}>
                      {t.stock_name}
                      <span style={{ fontSize: 9, color: '#4b5563', marginLeft: 5 }}>{t.stock_code}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 6, fontSize: 9, color: '#6b7280' }}>
                      <span><span style={{ color: '#16a34a', fontWeight: 600 }}>B</span> {t.buy_date} · {fmtPrice(t.buy_price)}</span>
                      <span style={{ color: '#374151' }}>→</span>
                      <span><span style={{ color: '#dc2626', fontWeight: 600 }}>S</span> {t.sell_date} · {fmtPrice(t.sell_price ?? 0)}</span>
                    </div>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: pctColor(t.return_pct ?? 0), flexShrink: 0, marginLeft: 10 }}>
                    {pctStr(t.return_pct ?? 0)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PerformanceSection;
