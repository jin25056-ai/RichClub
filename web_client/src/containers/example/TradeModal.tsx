import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { stockApi, tradeLogApi, TradeLogItem, StockItem } from '../../api/stock';

const fmt = (n: number) => Math.round(n).toLocaleString();
const fmtDateFull = (s: string) =>
  s ? new Date(s).toLocaleDateString('ko-KR', { year: '2-digit', month: '2-digit', day: '2-digit' }) : '';

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
    return { code, name, holding: totalBuyQty - totalSellQty, avgBuy, realized };
  });
};

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

interface EditState {
  id: string;
  price: string;
  quantity: string;
  memo: string;
}

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
  const [trash, setTrash] = useState<TradeLogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [rightTab, setRightTab] = useState<'logs' | 'trash'>('logs');

  // 폼 상태
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<StockItem[]>([]);
  const [selectedStock, setSelectedStock] = useState<StockItem | null>(null);
  const [tradeType, setTradeType] = useState<'buy' | 'sell'>('buy');
  const [price, setPrice] = useState('');
  const [quantity, setQuantity] = useState('');
  const [memo, setMemo] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // 인라인 수정 상태
  const [editState, setEditState] = useState<EditState | null>(null);
  const [saving, setSaving] = useState(false);

  const totalAmount = price && quantity ? Math.round(Number(price) * Number(quantity)) : 0;
  const pnlGroups = useMemo(() => calcPnL(logs), [logs]);
  const totalRealized = pnlGroups.reduce((s, g) => s + g.realized, 0);

  const overlayRef = React.useRef<HTMLDivElement>(null);
  const mouseDownTarget = React.useRef<EventTarget | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    fetchLogs();
    fetchTrash();
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

  const fetchTrash = () => {
    tradeLogApi.getTrash().then((r) => setTrash(r.data)).catch(() => {});
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
      setRightTab('logs');
    } finally {
      setSubmitting(false);
    }
  };

  // 휴지통으로 이동
  const handleDelete = async (id: string) => {
    await tradeLogApi.remove(id);
    setLogs((prev) => {
      const moved = prev.find((l) => l.id === id);
      if (moved) setTrash((t) => [moved, ...t]);
      return prev.filter((l) => l.id !== id);
    });
  };

  // 복구
  const handleRestore = async (id: string) => {
    const res = await tradeLogApi.restore(id);
    setTrash((prev) => prev.filter((l) => l.id !== id));
    setLogs((prev) => [res.data, ...prev]);
  };

  // 영구 삭제
  const handlePermanentDelete = async (id: string) => {
    if (!window.confirm('영구 삭제하시겠습니까? 복구할 수 없습니다.')) return;
    await tradeLogApi.permanentDelete(id);
    setTrash((prev) => prev.filter((l) => l.id !== id));
  };

  // 수정 시작
  const startEdit = (log: TradeLogItem) => {
    setEditState({ id: log.id, price: String(log.price), quantity: String(log.quantity), memo: log.memo ?? '' });
  };

  // 수정 저장
  const saveEdit = async () => {
    if (!editState) return;
    setSaving(true);
    try {
      const res = await tradeLogApi.update(editState.id, {
        price: Number(editState.price),
        quantity: Number(editState.quantity),
        memo: editState.memo,
      });
      setLogs((prev) => prev.map((l) => l.id === editState.id ? res.data : l));
      setEditState(null);
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  const input: React.CSSProperties = {
    width: '100%', background: '#0a0a14', border: '1px solid #2d2d3d', borderRadius: 6,
    color: '#e2e8f0', fontSize: 12, padding: '7px 10px', boxSizing: 'border-box', outline: 'none',
  };
  const inlineInput: React.CSSProperties = {
    background: '#0a0a14', border: '1px solid #3730a3', borderRadius: 4,
    color: '#e2e8f0', fontSize: 11, padding: '3px 6px', outline: 'none', width: '80px',
  };
  const lbl: React.CSSProperties = { fontSize: 10, color: '#6b7280', marginBottom: 3, display: 'block' };

  return (
    <div
      ref={overlayRef}
      onMouseDown={(e) => { mouseDownTarget.current = e.target; }}
      onClick={(e) => {
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
          width: 760, maxWidth: '95vw', maxHeight: '88vh',
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
                          onClick={async () => {
                            setSelectedStock(r); setQuery(''); setSearchResults([]);
                            try {
                              const res = await stockApi.getPrice(r.stock_code);
                              if (res.data.close) setPrice(String(Math.round(res.data.close)));
                            } catch {}
                          }}
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

            <div style={{ display: 'flex', gap: 8 }}>
              <div style={{ flex: 1 }}>
                <label style={lbl}>가격 (원)</label>
                <input style={input} type="number" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0" />
              </div>
              <div style={{ flex: 1 }}>
                <label style={lbl}>수량 (주)</label>
                <input style={input} type="number" value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="0" />
              </div>
            </div>
            <div style={{ fontSize: 11, color: totalAmount > 0 ? (tradeType === 'buy' ? '#4ade80' : '#f87171') : 'transparent', textAlign: 'right', minHeight: 16 }}>
              {totalAmount > 0 ? `총액 ${fmt(totalAmount)}원` : '.'}
            </div>

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

          {/* 우측 */}
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            {/* 탭 */}
            <div style={{ display: 'flex', borderBottom: '1px solid #1e1e2e', flexShrink: 0 }}>
              <button onClick={() => setRightTab('logs')}
                style={{
                  padding: '8px 16px', fontSize: 11, border: 'none', cursor: 'pointer', background: 'transparent',
                  color: rightTab === 'logs' ? '#a5b4fc' : '#555', fontWeight: rightTab === 'logs' ? 600 : 400,
                  borderBottom: rightTab === 'logs' ? '2px solid #6366f1' : '2px solid transparent',
                }}>
                매매 내역 {logs.length > 0 && <span style={{ fontSize: 9, color: '#6366f1' }}>{logs.length}</span>}
              </button>
              <button onClick={() => setRightTab('trash')}
                style={{
                  padding: '8px 16px', fontSize: 11, border: 'none', cursor: 'pointer', background: 'transparent',
                  color: rightTab === 'trash' ? '#f87171' : '#555', fontWeight: rightTab === 'trash' ? 600 : 400,
                  borderBottom: rightTab === 'trash' ? '2px solid #dc2626' : '2px solid transparent',
                }}>
                휴지통 {trash.length > 0 && <span style={{ fontSize: 9, color: '#dc2626' }}>{trash.length}</span>}
              </button>
            </div>

            {/* 보유 포지션 요약 */}
            {rightTab === 'logs' && pnlGroups.filter((g) => g.holding > 0).length > 0 && (
              <div style={{ padding: '8px 14px', borderBottom: '1px solid #1e1e2e', display: 'flex', gap: 6, flexWrap: 'wrap', flexShrink: 0 }}>
                {pnlGroups.filter((g) => g.holding > 0).map((g) => (
                  <div key={g.code} style={{ background: '#1e1e2e', borderRadius: 6, padding: '4px 8px', fontSize: 10 }}>
                    <span style={{ color: '#a5b4fc', fontWeight: 600 }}>{g.name}</span>
                    <span style={{ color: '#6b7280', marginLeft: 4 }}>{g.holding}주 · 평균 {fmt(g.avgBuy)}원</span>
                    {g.realized !== 0 && (
                      <span style={{ marginLeft: 4, color: g.realized > 0 ? '#4ade80' : '#f87171', fontWeight: 600 }}>
                        {g.realized > 0 ? '+' : ''}{fmt(g.realized)}원
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* 매매 내역 */}
            {rightTab === 'logs' && (
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
                          <th key={h} style={{ padding: '8px 8px', textAlign: 'left', color: '#6b7280', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {logs.map((log) => {
                        const isEditing = editState?.id === log.id;
                        return (
                          <tr key={log.id} style={{ borderBottom: '1px solid #13131e' }}
                            onMouseEnter={(e) => { if (!isEditing) e.currentTarget.style.background = '#151525'; }}
                            onMouseLeave={(e) => { if (!isEditing) e.currentTarget.style.background = 'transparent'; }}>
                            <td style={{ padding: '7px 8px', color: '#6b7280', whiteSpace: 'nowrap' }}>{fmtDateFull(log.traded_at)}</td>
                            <td style={{ padding: '7px 8px', fontWeight: 500, whiteSpace: 'nowrap' }}>{log.stock_name}</td>
                            <td style={{ padding: '7px 8px' }}>
                              <span style={{
                                fontSize: 9, padding: '2px 5px', borderRadius: 3, fontWeight: 600,
                                background: log.trade_type === 'buy' ? '#14532d' : '#7f1d1d',
                                color: log.trade_type === 'buy' ? '#4ade80' : '#f87171',
                              }}>
                                {log.trade_type === 'buy' ? '매수' : '매도'}
                              </span>
                            </td>
                            {isEditing ? (
                              <>
                                <td style={{ padding: '4px 6px' }}>
                                  <input style={inlineInput} type="number" value={editState.price}
                                    onChange={(e) => setEditState({ ...editState, price: e.target.value })} />
                                </td>
                                <td style={{ padding: '4px 6px' }}>
                                  <input style={{ ...inlineInput, width: 56 }} type="number" value={editState.quantity}
                                    onChange={(e) => setEditState({ ...editState, quantity: e.target.value })} />
                                </td>
                                <td style={{ padding: '4px 6px', color: '#6b7280', fontSize: 10 }}>
                                  {editState.price && editState.quantity
                                    ? fmt(Math.round(Number(editState.price) * Number(editState.quantity)))
                                    : '-'}
                                </td>
                                <td style={{ padding: '4px 6px' }}>
                                  <input style={{ ...inlineInput, width: 100 }} value={editState.memo}
                                    onChange={(e) => setEditState({ ...editState, memo: e.target.value })} />
                                </td>
                                <td style={{ padding: '4px 6px', whiteSpace: 'nowrap' }}>
                                  <button onClick={saveEdit} disabled={saving}
                                    style={{ fontSize: 10, padding: '2px 6px', borderRadius: 3, border: 'none', cursor: 'pointer', background: '#6366f1', color: '#fff', marginRight: 3 }}>
                                    {saving ? '...' : '저장'}
                                  </button>
                                  <button onClick={() => setEditState(null)}
                                    style={{ fontSize: 10, padding: '2px 6px', borderRadius: 3, border: 'none', cursor: 'pointer', background: '#1e1e2e', color: '#888' }}>
                                    취소
                                  </button>
                                </td>
                              </>
                            ) : (
                              <>
                                <td style={{ padding: '7px 8px', textAlign: 'right', whiteSpace: 'nowrap' }}>{fmt(log.price)}</td>
                                <td style={{ padding: '7px 8px', textAlign: 'right' }}>{log.quantity}</td>
                                <td style={{ padding: '7px 8px', textAlign: 'right', whiteSpace: 'nowrap', fontWeight: 500 }}>{fmt(log.total_amount)}</td>
                                <td style={{ padding: '7px 8px', color: '#6b7280', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{log.memo || '-'}</td>
                                <td style={{ padding: '7px 6px', whiteSpace: 'nowrap' }}>
                                  <button onClick={() => startEdit(log)} title="수정"
                                    style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 12, marginRight: 2 }}>
                                    ✎
                                  </button>
                                  <button onClick={() => handleDelete(log.id)} title="휴지통으로"
                                    style={{ background: 'none', border: 'none', color: '#4b5563', cursor: 'pointer', fontSize: 13 }}>
                                    🗑
                                  </button>
                                </td>
                              </>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {/* 휴지통 */}
            {rightTab === 'trash' && (
              <div style={{ flex: 1, overflowY: 'auto' }}>
                {trash.length === 0 ? (
                  <div style={{ padding: 40, fontSize: 12, color: '#4b5563', textAlign: 'center' }}>
                    휴지통이 비어있습니다.
                  </div>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                    <thead style={{ position: 'sticky', top: 0, background: '#0f0f1a', zIndex: 1 }}>
                      <tr style={{ borderBottom: '1px solid #1e1e2e' }}>
                        {['날짜', '종목', '구분', '가격', '수량', '총액', '메모', ''].map((h) => (
                          <th key={h} style={{ padding: '8px 8px', textAlign: 'left', color: '#6b7280', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {trash.map((log) => (
                        <tr key={log.id} style={{ borderBottom: '1px solid #13131e', opacity: 0.6 }}
                          onMouseEnter={(e) => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.background = '#151525'; }}
                          onMouseLeave={(e) => { e.currentTarget.style.opacity = '0.6'; e.currentTarget.style.background = 'transparent'; }}>
                          <td style={{ padding: '7px 8px', color: '#6b7280', whiteSpace: 'nowrap' }}>{fmtDateFull(log.traded_at)}</td>
                          <td style={{ padding: '7px 8px', fontWeight: 500, whiteSpace: 'nowrap' }}>{log.stock_name}</td>
                          <td style={{ padding: '7px 8px' }}>
                            <span style={{
                              fontSize: 9, padding: '2px 5px', borderRadius: 3, fontWeight: 600,
                              background: log.trade_type === 'buy' ? '#14532d' : '#7f1d1d',
                              color: log.trade_type === 'buy' ? '#4ade80' : '#f87171',
                            }}>
                              {log.trade_type === 'buy' ? '매수' : '매도'}
                            </span>
                          </td>
                          <td style={{ padding: '7px 8px', textAlign: 'right', whiteSpace: 'nowrap' }}>{fmt(log.price)}</td>
                          <td style={{ padding: '7px 8px', textAlign: 'right' }}>{log.quantity}</td>
                          <td style={{ padding: '7px 8px', textAlign: 'right', whiteSpace: 'nowrap' }}>{fmt(log.total_amount)}</td>
                          <td style={{ padding: '7px 8px', color: '#6b7280', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{log.memo || '-'}</td>
                          <td style={{ padding: '7px 6px', whiteSpace: 'nowrap' }}>
                            <button onClick={() => handleRestore(log.id)} title="복구"
                              style={{ fontSize: 10, padding: '2px 6px', borderRadius: 3, border: '1px solid #374151', cursor: 'pointer', background: 'transparent', color: '#9ca3af', marginRight: 4 }}>
                              복구
                            </button>
                            <button onClick={() => handlePermanentDelete(log.id)} title="영구 삭제"
                              style={{ background: 'none', border: 'none', color: '#7f1d1d', cursor: 'pointer', fontSize: 13 }}>
                              ×
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default TradeModal;
