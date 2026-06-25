import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { stockApi, tradeLogApi, TradeLogItem, StockItem } from '../../api/stock';

const fmt = (n: number) => Math.round(n).toLocaleString();
const fmtDateFull = (s: string) =>
  s ? new Date(s).toLocaleDateString('ko-KR', { year: '2-digit', month: '2-digit', day: '2-digit' }) : '';

// 매수-매도 매칭 손익 계산
const calcPnL = (logs: TradeLogItem[]) => {
  const groups: Record<string, { buys: TradeLogItem[]; sells: TradeLogItem[] }> = {};
  for (const log of logs) {
    if (!groups[log.stock_code]) groups[log.stock_code] = { buys: [], sells: [] };
    if (log.trade_type === 'buy') groups[log.stock_code].buys.push(log);
    else groups[log.stock_code].sells.push(log);
  }
  return Object.entries(groups).map(([code, { buys, sells }]) => {
    const name = buys[0]?.stock_name ?? sells[0]?.stock_name ?? code;
    const totalBuyQty = buys.reduce((s, b) => s + b.quantity, 0);
    const totalSellQty = sells.reduce((s, b) => s + b.quantity, 0);
    const avgBuy = totalBuyQty > 0 ? buys.reduce((s, b) => s + b.total_amount, 0) / totalBuyQty : 0;
    const realized = sells.reduce((s, b) => s + b.total_amount, 0) - avgBuy * totalSellQty;
    return { code, name, holding: totalBuyQty - totalSellQty, avgBuy, realized, logs: [...buys, ...sells].sort((a, b) => new Date(a.traded_at).getTime() - new Date(b.traded_at).getTime()) };
  });
};

// CSV 내보내기
const exportCSV = (logs: TradeLogItem[]) => {
  const header = ['날짜', '종목명', '종목코드', '구분', '가격', '수량', '총액', '메모'];
  const rows = logs.map((l) => [
    fmtDateFull(l.traded_at), l.stock_name, l.stock_code,
    l.trade_type === 'buy' ? '매수' : '매도',
    l.price, l.quantity, l.total_amount, l.memo ?? '',
  ]);
  const csv = [header, ...rows].map((r) => r.map((v) => `"${v}"`).join(',')).join('\n');
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `매매일지_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click(); URL.revokeObjectURL(url);
};

interface Props {
  isOpen: boolean;
  onClose: () => void;
  initialStockCode?: string;
  initialStockName?: string;
  initialPrice?: number;
}

const TradeModal: React.FC<Props> = ({ isOpen, onClose, initialStockCode, initialStockName, initialPrice }) => {
  const navigate = useNavigate();
  const [logs, setLogs] = useState<TradeLogItem[]>([]);
  const [loading, setLoading] = useState(false);

  // 폼 상태
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<StockItem[]>([]);
  const [selectedStock, setSelectedStock] = useState<StockItem | null>(null);
  const [tradeType, setTradeType] = useState<'buy' | 'sell'>('buy');
  const [price, setPrice] = useState('');
  const [quantity, setQuantity] = useState('');
  const [memo, setMemo] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<'form' | 'list'>('form');

  const totalAmount = price && quantity ? Math.round(Number(price) * Number(quantity)) : 0;
  const pnlGroups = useMemo(() => calcPnL(logs), [logs]);
  const totalRealized = pnlGroups.reduce((s, g) => s + g.realized, 0);

  // 모달 열릴 때 현재 종목/가격 자동 입력
  useEffect(() => {
    if (!isOpen) return;
    fetchLogs();
    if (initialStockCode && initialStockName) {
      setSelectedStock({ stock_code: initialStockCode, stock_name: initialStockName });
      setQuery('');
    }
    if (initialPrice) setPrice(String(initialPrice));
  }, [isOpen, initialStockCode, initialStockName, initialPrice]);

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
      setPrice(''); setQuantity(''); setMemo('');
      fetchLogs();
      setActiveTab('list');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    await tradeLogApi.remove(id);
    setLogs((prev) => prev.filter((l) => l.id !== id));
  };

  const overlayRef = React.useRef<HTMLDivElement>(null);
  const mouseDownTarget = React.useRef<EventTarget | null>(null);

  if (!isOpen) return null;

  const input: React.CSSProperties = {
    width: '100%', background: '#0a0a14', border: '1px solid #2d2d3d', borderRadius: 6,
    color: '#e2e8f0', fontSize: 12, padding: '7px 10px', boxSizing: 'border-box',
    outline: 'none',
  };
  const lbl: React.CSSProperties = { fontSize: 10, color: '#6b7280', marginBottom: 3, display: 'block' };

  return (
    <div
      ref={overlayRef}
      onMouseDown={(e) => { mouseDownTarget.current = e.target; }}
      onClick={(e) => {
        // 드래그로 모달 밖에서 mouseup 됐을 때 닫히지 않도록
        // mousedown 시작이 오버레이 자체일 때만 닫기
        if (e.target === overlayRef.current && mouseDownTarget.current === overlayRef.current) onClose();
      }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 12,
          width: 720, maxWidth: '95vw', maxHeight: '88vh',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          boxShadow: '0 24px 64px rgba(0,0,0,0.8)',
        }}
      >
        {/* 헤더 */}
        <div style={{ display: 'flex', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid #1e1e2e', flexShrink: 0 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0' }}>매매일지</span>
          {totalRealized !== 0 && (
            <span style={{
              marginLeft: 10, fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 4,
              background: totalRealized > 0 ? '#14532d' : '#7f1d1d',
              color: totalRealized > 0 ? '#4ade80' : '#f87171',
            }}>
              실현손익 {totalRealized > 0 ? '+' : ''}{fmt(totalRealized)}원
            </span>
          )}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
            <button onClick={() => exportCSV(logs)}
              style={{ fontSize: 10, padding: '3px 8px', background: '#1e1e2e', color: '#6b7280', border: '1px solid #2d2d3d', borderRadius: 4, cursor: 'pointer' }}>
              CSV 내보내기
            </button>
            <button onClick={() => { onClose(); navigate('/trade'); }}
              style={{ fontSize: 10, padding: '3px 8px', background: '#1e1e2e', color: '#a5b4fc', border: '1px solid #3730a3', borderRadius: 4, cursor: 'pointer' }}>
              크게 보기
            </button>
            <button onClick={onClose}
              style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>
              ×
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
          {/* 좌측 - 입력 폼 */}
          <div style={{ width: 240, flexShrink: 0, padding: '16px', borderRight: '1px solid #1e1e2e', display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto' }}>
            {/* 매수/매도 토글 */}
            <div style={{ display: 'flex', borderRadius: 6, overflow: 'hidden', border: '1px solid #2d2d3d' }}>
              {(['buy', 'sell'] as const).map((t) => (
                <button key={t} onClick={() => setTradeType(t)}
                  style={{
                    flex: 1, padding: '7px 0', fontSize: 12, fontWeight: 600, border: 'none', cursor: 'pointer',
                    background: tradeType === t ? (t === 'buy' ? '#14532d' : '#7f1d1d') : 'transparent',
                    color: tradeType === t ? (t === 'buy' ? '#4ade80' : '#f87171') : '#555',
                  }}>
                  {t === 'buy' ? '매수' : '매도'}
                </button>
              ))}
            </div>

            {/* 종목 */}
            <div style={{ position: 'relative' }}>
              <label style={lbl}>종목</label>
              {selectedStock ? (
                <div style={{ display: 'flex', alignItems: 'center', background: '#0a0a14', border: '1px solid #6366f1', borderRadius: 6, padding: '7px 10px' }}>
                  <span style={{ flex: 1, fontSize: 12 }}>{selectedStock.stock_name}</span>
                  <button onClick={() => { setSelectedStock(null); setQuery(''); setPrice(''); }}
                    style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 14 }}>×</button>
                </div>
              ) : (
                <>
                  <input style={input} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="종목명 검색" />
                  {searchResults.length > 0 && (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10, marginTop: 2,
                      background: '#1a1a2e', border: '1px solid #2d2d3d', borderRadius: 6,
                      maxHeight: 140, overflowY: 'auto', boxShadow: '0 4px 16px rgba(0,0,0,0.6)',
                    }}>
                      {searchResults.map((r) => (
                        <div key={r.stock_code}
                          onClick={() => { setSelectedStock(r); setQuery(''); setSearchResults([]); }}
                          style={{ padding: '7px 10px', cursor: 'pointer', fontSize: 11, borderBottom: '1px solid #1e1e2e' }}
                          onMouseEnter={(e) => (e.currentTarget.style.background = '#2d2d3d')}
                          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                          <span style={{ color: '#d1d5db' }}>{r.stock_name}</span>
                          <span style={{ color: '#4b5563', marginLeft: 5, fontSize: 9 }}>{r.stock_code}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* 가격 */}
            <div>
              <label style={lbl}>가격 (원)</label>
              <input style={input} type="number" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0" />
            </div>

            {/* 수량 */}
            <div>
              <label style={lbl}>수량 (주)</label>
              <input style={input} type="number" value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="0" />
            </div>

            {/* 총액 */}
            {totalAmount > 0 && (
              <div style={{ padding: '7px 10px', background: '#1e1e2e', borderRadius: 6, fontSize: 11 }}>
                <span style={{ color: '#6b7280' }}>총액</span>
                <span style={{ float: 'right', fontWeight: 600, color: tradeType === 'buy' ? '#4ade80' : '#f87171' }}>
                  {fmt(totalAmount)}원
                </span>
              </div>
            )}

            {/* 메모 */}
            <div>
              <label style={lbl}>메모 (선택)</label>
              <textarea style={{ ...input, resize: 'none', height: 56 } as React.CSSProperties}
                value={memo} onChange={(e) => setMemo(e.target.value)} placeholder="진입 이유, 목표가 등" />
            </div>

            <button onClick={handleSubmit} disabled={submitting || !selectedStock || !price || !quantity}
              style={{
                padding: '9px 0', borderRadius: 6, border: 'none', cursor: 'pointer',
                fontSize: 12, fontWeight: 600, marginTop: 'auto',
                background: (!selectedStock || !price || !quantity) ? '#1e1e2e'
                  : tradeType === 'buy' ? '#16a34a' : '#dc2626',
                color: (!selectedStock || !price || !quantity) ? '#555' : '#fff',
              }}>
              {submitting ? '저장 중...' : `${tradeType === 'buy' ? '매수' : '매도'} 기록 추가`}
            </button>
          </div>

          {/* 우측 - 매매 내역 */}
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            {/* 보유 포지션 요약 */}
            {pnlGroups.filter((g) => g.holding > 0).length > 0 && (
              <div style={{ padding: '10px 14px', borderBottom: '1px solid #1e1e2e', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {pnlGroups.filter((g) => g.holding > 0).map((g) => (
                  <div key={g.code} style={{ background: '#1e1e2e', borderRadius: 6, padding: '5px 10px', fontSize: 10 }}>
                    <span style={{ color: '#a5b4fc', fontWeight: 600 }}>{g.name}</span>
                    <span style={{ color: '#6b7280', marginLeft: 5 }}>{g.holding}주 · 평균 {fmt(g.avgBuy)}원</span>
                    {g.realized !== 0 && (
                      <span style={{ marginLeft: 5, color: g.realized > 0 ? '#4ade80' : '#f87171', fontWeight: 600 }}>
                        {g.realized > 0 ? '+' : ''}{fmt(g.realized)}원
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* 매매 내역 테이블 */}
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {loading ? (
                <div style={{ padding: 20, fontSize: 12, color: '#6b7280', textAlign: 'center' }}>불러오는 중...</div>
              ) : logs.length === 0 ? (
                <div style={{ padding: 40, fontSize: 12, color: '#4b5563', textAlign: 'center' }}>
                  매매 기록이 없습니다.<br />왼쪽에서 거래를 추가하세요.
                </div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                  <thead style={{ position: 'sticky', top: 0, background: '#0f0f1a', zIndex: 1 }}>
                    <tr style={{ borderBottom: '1px solid #1e1e2e' }}>
                      {['날짜', '종목', '구분', '가격', '수량', '총액', '메모', ''].map((h) => (
                        <th key={h} style={{ padding: '8px 10px', textAlign: 'left', color: '#6b7280', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log) => (
                      <tr key={log.id} style={{ borderBottom: '1px solid #13131e' }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = '#151525')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                        <td style={{ padding: '7px 10px', color: '#6b7280', whiteSpace: 'nowrap' }}>{fmtDateFull(log.traded_at)}</td>
                        <td style={{ padding: '7px 10px', fontWeight: 500, whiteSpace: 'nowrap' }}>{log.stock_name}</td>
                        <td style={{ padding: '7px 10px' }}>
                          <span style={{
                            fontSize: 9, padding: '2px 5px', borderRadius: 3, fontWeight: 600,
                            background: log.trade_type === 'buy' ? '#14532d' : '#7f1d1d',
                            color: log.trade_type === 'buy' ? '#4ade80' : '#f87171',
                          }}>
                            {log.trade_type === 'buy' ? '매수' : '매도'}
                          </span>
                        </td>
                        <td style={{ padding: '7px 10px', textAlign: 'right', whiteSpace: 'nowrap' }}>{fmt(log.price)}</td>
                        <td style={{ padding: '7px 10px', textAlign: 'right' }}>{log.quantity}</td>
                        <td style={{ padding: '7px 10px', textAlign: 'right', whiteSpace: 'nowrap', fontWeight: 500 }}>{fmt(log.total_amount)}</td>
                        <td style={{ padding: '7px 10px', color: '#6b7280', maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{log.memo || '-'}</td>
                        <td style={{ padding: '7px 6px' }}>
                          <button onClick={() => handleDelete(log.id)}
                            style={{ background: 'none', border: 'none', color: '#4b5563', cursor: 'pointer', fontSize: 13 }}>×</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TradeModal;
