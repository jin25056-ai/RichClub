import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { stockApi, tradeLogApi, TradeLogItem, StockItem } from '../api/stock';

const fmt = (n: number) => Math.round(n).toLocaleString();
const fmtDate = (s: string) => s ? new Date(s).toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit' }) : '';
const fmtDateFull = (s: string) => s ? new Date(s).toLocaleDateString('ko-KR', { year: '2-digit', month: '2-digit', day: '2-digit' }) : '';

type ViewMode = 'timeline' | 'grouped';

// 매수-매도 매칭으로 손익 계산
const calcPnL = (logs: TradeLogItem[]) => {
  const result: { code: string; name: string; buyLogs: TradeLogItem[]; sellLogs: TradeLogItem[]; holding: number; avgBuy: number; realized: number; unrealizedQty: number }[] = [];
  const groups: Record<string, { buys: TradeLogItem[]; sells: TradeLogItem[] }> = {};
  for (const log of logs) {
    if (!groups[log.stock_code]) groups[log.stock_code] = { buys: [], sells: [] };
    if (log.trade_type === 'buy') groups[log.stock_code].buys.push(log);
    else groups[log.stock_code].sells.push(log);
  }
  for (const [code, { buys, sells }] of Object.entries(groups)) {
    const name = buys[0]?.stock_name ?? sells[0]?.stock_name ?? code;
    const totalBuyQty = buys.reduce((s, b) => s + b.quantity, 0);
    const totalSellQty = sells.reduce((s, b) => s + b.quantity, 0);
    const totalBuyAmt = buys.reduce((s, b) => s + b.total_amount, 0);
    const avgBuy = totalBuyQty > 0 ? totalBuyAmt / totalBuyQty : 0;
    const totalSellAmt = sells.reduce((s, b) => s + b.total_amount, 0);
    const soldCost = avgBuy * totalSellQty;
    const realized = totalSellAmt - soldCost;
    result.push({ code, name, buyLogs: buys, sellLogs: sells, holding: totalBuyQty - totalSellQty, avgBuy, realized, unrealizedQty: Math.max(0, totalBuyQty - totalSellQty) });
  }
  return result;
};

const TradePage: React.FC = () => {
  const navigate = useNavigate();
  const [logs, setLogs] = useState<TradeLogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('timeline');

  // 폼 상태
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<StockItem[]>([]);
  const [selectedStock, setSelectedStock] = useState<StockItem | null>(null);
  const [tradeType, setTradeType] = useState<'buy' | 'sell'>('buy');
  const [price, setPrice] = useState('');
  const [quantity, setQuantity] = useState('');
  const [memo, setMemo] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const totalAmount = price && quantity ? Math.round(Number(price) * Number(quantity)) : 0;

  useEffect(() => {
    if (!localStorage.getItem('access_token')) { navigate('/auth'); return; }
    fetchLogs();
  }, []);

  useEffect(() => {
    if (!query.trim()) { setSearchResults([]); return; }
    const t = setTimeout(() => {
      stockApi.search(query).then((r) => setSearchResults(r.data));
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  const fetchLogs = () => {
    setLoading(true);
    tradeLogApi.get().then((r) => setLogs(r.data)).finally(() => setLoading(false));
  };

  const handleSubmit = async () => {
    if (!selectedStock || !price || !quantity) return;
    setSubmitting(true);
    try {
      await tradeLogApi.create({
        stock_code: selectedStock.stock_code,
        stock_name: selectedStock.stock_name,
        trade_type: tradeType,
        price: Number(price),
        quantity: Number(quantity),
        memo: memo || undefined,
      });
      setSelectedStock(null); setQuery(''); setPrice(''); setQuantity(''); setMemo('');
      fetchLogs();
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('삭제하시겠습니까?')) return;
    await tradeLogApi.remove(id);
    setLogs((prev) => prev.filter((l) => l.id !== id));
  };

  const pnlGroups = useMemo(() => calcPnL(logs), [logs]);
  const totalRealized = pnlGroups.reduce((s, g) => s + g.realized, 0);

  const panel = { background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: '16px' };
  const input = {
    width: '100%', background: '#0a0a14', border: '1px solid #2d2d3d', borderRadius: 6,
    color: '#e2e8f0', fontSize: 13, padding: '8px 10px', boxSizing: 'border-box' as const,
  };
  const label = { fontSize: 11, color: '#6b7280', marginBottom: 4, display: 'block' as const };

  return (
    <div style={{ background: '#0a0a14', minHeight: '100vh', padding: '16px', fontFamily: 'inherit', color: '#e2e8f0' }}>
      {/* 헤더 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <button onClick={() => navigate('/')}
          style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 18, padding: 0 }}>
          ←
        </button>
        <h1 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>매매일지</h1>
        {totalRealized !== 0 && (
          <span style={{
            fontSize: 12, fontWeight: 600, padding: '2px 8px', borderRadius: 4,
            background: totalRealized > 0 ? '#14532d' : '#7f1d1d',
            color: totalRealized > 0 ? '#4ade80' : '#f87171',
          }}>
            실현손익 {totalRealized > 0 ? '+' : ''}{fmt(totalRealized)}원
          </span>
        )}
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* 좌측 - 입력 폼 */}
        <div style={{ width: 280, flexShrink: 0, ...panel }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14, color: '#a5b4fc' }}>거래 추가</div>

          {/* 매수/매도 토글 */}
          <div style={{ display: 'flex', marginBottom: 14, borderRadius: 6, overflow: 'hidden', border: '1px solid #2d2d3d' }}>
            {(['buy', 'sell'] as const).map((t) => (
              <button key={t} onClick={() => setTradeType(t)}
                style={{
                  flex: 1, padding: '8px 0', fontSize: 12, fontWeight: 600, border: 'none', cursor: 'pointer',
                  background: tradeType === t ? (t === 'buy' ? '#14532d' : '#7f1d1d') : 'transparent',
                  color: tradeType === t ? (t === 'buy' ? '#4ade80' : '#f87171') : '#555',
                }}>
                {t === 'buy' ? '매수' : '매도'}
              </button>
            ))}
          </div>

          {/* 종목 검색 */}
          <div style={{ marginBottom: 12, position: 'relative' }}>
            <label style={label}>종목</label>
            {selectedStock ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#0a0a14', border: '1px solid #6366f1', borderRadius: 6, padding: '8px 10px' }}>
                <span style={{ flex: 1, fontSize: 13 }}>{selectedStock.stock_name}</span>
                <button onClick={() => { setSelectedStock(null); setQuery(''); }}
                  style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 14 }}>×</button>
              </div>
            ) : (
              <>
                <input style={input} value={query} onChange={(e) => setQuery(e.target.value)}
                  placeholder="종목명 또는 코드 검색" />
                {searchResults.length > 0 && (
                  <div style={{
                    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 999, marginTop: 2,
                    background: '#1a1a2e', border: '1px solid #2d2d3d', borderRadius: 6,
                    maxHeight: 160, overflowY: 'auto', boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
                  }}>
                    {searchResults.map((r) => (
                      <div key={r.stock_code}
                        onClick={() => { setSelectedStock(r); setQuery(''); setSearchResults([]); }}
                        style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 12, borderBottom: '1px solid #1e1e2e' }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = '#2d2d3d')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                        <span style={{ color: '#d1d5db' }}>{r.stock_name}</span>
                        <span style={{ color: '#4b5563', marginLeft: 6, fontSize: 10 }}>{r.stock_code}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          {/* 가격 */}
          <div style={{ marginBottom: 12 }}>
            <label style={label}>가격 (원)</label>
            <input style={input} type="number" value={price}
              onChange={(e) => setPrice(e.target.value)} placeholder="0" />
          </div>

          {/* 수량 */}
          <div style={{ marginBottom: 12 }}>
            <label style={label}>수량 (주)</label>
            <input style={input} type="number" value={quantity}
              onChange={(e) => setQuantity(e.target.value)} placeholder="0" />
          </div>

          {/* 총액 */}
          {totalAmount > 0 && (
            <div style={{ marginBottom: 12, padding: '8px 10px', background: '#1e1e2e', borderRadius: 6, fontSize: 12 }}>
              <span style={{ color: '#6b7280' }}>총액</span>
              <span style={{ float: 'right', fontWeight: 600, color: tradeType === 'buy' ? '#4ade80' : '#f87171' }}>
                {fmt(totalAmount)}원
              </span>
            </div>
          )}

          {/* 메모 */}
          <div style={{ marginBottom: 16 }}>
            <label style={label}>메모 (선택)</label>
            <textarea style={{ ...input, resize: 'vertical', minHeight: 60 } as React.CSSProperties}
              value={memo} onChange={(e) => setMemo(e.target.value)} placeholder="진입 이유, 목표가 등" />
          </div>

          <button onClick={handleSubmit} disabled={submitting || !selectedStock || !price || !quantity}
            style={{
              width: '100%', padding: '10px 0', borderRadius: 6, border: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: 600,
              background: (!selectedStock || !price || !quantity) ? '#1e1e2e'
                : tradeType === 'buy' ? '#16a34a' : '#dc2626',
              color: (!selectedStock || !price || !quantity) ? '#555' : '#fff',
            }}>
            {submitting ? '저장 중...' : `${tradeType === 'buy' ? '매수' : '매도'} 기록 추가`}
          </button>
        </div>

        {/* 우측 - 매매 내역 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* 보유 포지션 요약 */}
          {pnlGroups.filter((g) => g.holding > 0).length > 0 && (
            <div style={{ ...panel, marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#a5b4fc', marginBottom: 10 }}>보유 중</div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {pnlGroups.filter((g) => g.holding > 0).map((g) => (
                  <div key={g.code} style={{
                    background: '#1e1e2e', borderRadius: 6, padding: '8px 12px', fontSize: 11,
                    border: '1px solid #2d2d3d',
                  }}>
                    <div style={{ fontWeight: 600, color: '#d1d5db', marginBottom: 2 }}>{g.name}</div>
                    <div style={{ color: '#6b7280' }}>{g.holding}주 · 평균 {fmt(g.avgBuy)}원</div>
                    {g.realized !== 0 && (
                      <div style={{ color: g.realized > 0 ? '#4ade80' : '#f87171', fontSize: 10, marginTop: 2 }}>
                        실현 {g.realized > 0 ? '+' : ''}{fmt(g.realized)}원
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 뷰 모드 토글 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 12, color: '#6b7280' }}>전체 {logs.length}건</span>
            <div style={{ display: 'flex', gap: 4 }}>
              {(['timeline', 'grouped'] as const).map((m) => (
                <button key={m} onClick={() => setViewMode(m)}
                  style={{
                    padding: '3px 10px', fontSize: 11, borderRadius: 4, border: 'none', cursor: 'pointer',
                    background: viewMode === m ? '#6366f1' : '#1e1e2e',
                    color: viewMode === m ? '#fff' : '#888',
                  }}>
                  {m === 'timeline' ? '시간순' : '종목별'}
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <div style={{ ...panel, color: '#6b7280', fontSize: 12, textAlign: 'center', padding: 30 }}>불러오는 중...</div>
          ) : logs.length === 0 ? (
            <div style={{ ...panel, color: '#4b5563', fontSize: 12, textAlign: 'center', padding: 40 }}>
              매매 기록이 없습니다.<br />왼쪽 폼에서 거래를 추가하세요.
            </div>
          ) : viewMode === 'timeline' ? (
            // 시간순 뷰
            <div style={{ ...panel, padding: 0, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #1e1e2e' }}>
                    {['날짜', '종목', '구분', '가격', '수량', '총액', '메모', ''].map((h) => (
                      <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: '#6b7280', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id} style={{ borderBottom: '1px solid #13131e' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = '#151525')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                      <td style={{ padding: '9px 12px', color: '#6b7280', whiteSpace: 'nowrap' }}>{fmtDateFull(log.traded_at)}</td>
                      <td style={{ padding: '9px 12px', fontWeight: 500 }}>{log.stock_name}</td>
                      <td style={{ padding: '9px 12px' }}>
                        <span style={{
                          fontSize: 10, padding: '2px 6px', borderRadius: 3, fontWeight: 600,
                          background: log.trade_type === 'buy' ? '#14532d' : '#7f1d1d',
                          color: log.trade_type === 'buy' ? '#4ade80' : '#f87171',
                        }}>
                          {log.trade_type === 'buy' ? '매수' : '매도'}
                        </span>
                      </td>
                      <td style={{ padding: '9px 12px', textAlign: 'right', whiteSpace: 'nowrap' }}>{fmt(log.price)}</td>
                      <td style={{ padding: '9px 12px', textAlign: 'right' }}>{log.quantity}</td>
                      <td style={{ padding: '9px 12px', textAlign: 'right', whiteSpace: 'nowrap', fontWeight: 500 }}>{fmt(log.total_amount)}</td>
                      <td style={{ padding: '9px 12px', color: '#6b7280', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{log.memo || '-'}</td>
                      <td style={{ padding: '9px 8px' }}>
                        <button onClick={() => handleDelete(log.id)}
                          style={{ background: 'none', border: 'none', color: '#4b5563', cursor: 'pointer', fontSize: 13 }}>×</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            // 종목별 그룹 뷰
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {pnlGroups.map((g) => (
                <div key={g.code} style={panel}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <div>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{g.name}</span>
                      <span style={{ fontSize: 10, color: '#4b5563', marginLeft: 6 }}>{g.code}</span>
                    </div>
                    <div style={{ textAlign: 'right', fontSize: 11 }}>
                      {g.holding > 0 && <div style={{ color: '#a5b4fc' }}>보유 {g.holding}주 · 평균 {fmt(g.avgBuy)}원</div>}
                      {g.realized !== 0 && (
                        <div style={{ color: g.realized > 0 ? '#4ade80' : '#f87171', fontWeight: 600 }}>
                          실현 {g.realized > 0 ? '+' : ''}{fmt(g.realized)}원
                        </div>
                      )}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {[...g.buyLogs, ...g.sellLogs]
                      .sort((a, b) => new Date(a.traded_at).getTime() - new Date(b.traded_at).getTime())
                      .map((log) => (
                        <div key={log.id} style={{
                          display: 'flex', alignItems: 'center', gap: 8,
                          padding: '6px 8px', borderRadius: 4, background: '#0a0a14', fontSize: 11,
                        }}>
                          <span style={{ color: '#6b7280', flexShrink: 0 }}>{fmtDate(log.traded_at)}</span>
                          <span style={{
                            fontSize: 9, padding: '1px 5px', borderRadius: 3, fontWeight: 600, flexShrink: 0,
                            background: log.trade_type === 'buy' ? '#14532d' : '#7f1d1d',
                            color: log.trade_type === 'buy' ? '#4ade80' : '#f87171',
                          }}>
                            {log.trade_type === 'buy' ? '매수' : '매도'}
                          </span>
                          <span style={{ color: '#9ca3af' }}>{fmt(log.price)}원 × {log.quantity}주</span>
                          <span style={{ fontWeight: 500 }}>{fmt(log.total_amount)}원</span>
                          {log.memo && <span style={{ color: '#4b5563', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{log.memo}</span>}
                          <button onClick={() => handleDelete(log.id)}
                            style={{ background: 'none', border: 'none', color: '#374151', cursor: 'pointer', fontSize: 12, flexShrink: 0 }}>×</button>
                        </div>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TradePage;
