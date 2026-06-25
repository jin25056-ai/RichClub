import React, { useState, useEffect, useCallback } from 'react';
import { stockApi, watchlistApi, AIPredictionItem, WatchlistItem } from '../../api/stock';

const SIGNAL_COLOR: Record<string, string> = { 매수: '#16a34a', 매도: '#dc2626', 관망: '#d97706' };
const SIGNAL_BG: Record<string, string> = { 매수: '#14532d', 매도: '#7f1d1d', 관망: '#78350f' };

interface Props {
  onSelectStock: (stockCode: string, stockName: string) => void;
  selectedCode?: string;
  onWatchChange?: (code: string, id: string | null) => void;
}

const fmtPrice = (p: number) =>
  p >= 1000000 ? `${(p / 1000000).toFixed(1)}M`
  : p >= 1000  ? `${Math.round(p / 1000)}K`
  : String(p);

const fmtDate = (s: string) => {
  if (!s) return '';
  const d = new Date(s);
  return `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
};

const UpdateNotice: React.FC = () => (
  <div style={{ padding: '5px 10px', borderBottom: '1px solid #1e1e2e', fontSize: 10, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 6 }}>
    <span style={{ color: '#4b5563', fontWeight: 600, flexShrink: 0 }}>갱신 주기</span>
    <span style={{ whiteSpace: 'nowrap' }}>
      차트 · AI 예측&nbsp;
      <span style={{ color: '#818cf8' }}>매일 15:35</span>
    </span>
  </div>
);

const RightPanel: React.FC<Props> = ({ onSelectStock, selectedCode, onWatchChange }) => {
  const [tab, setTab] = useState<'ai' | 'watchlist'>('ai');

  // AI 예측 상태
  const [items, setItems] = useState<AIPredictionItem[]>([]);
  const [filter, setFilter] = useState<'' | '매수' | '매도' | '관망'>('');
  const [loading, setLoading] = useState(false);

  // 관심종목 상태
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [watchIds, setWatchIds] = useState<Record<string, string>>({}); // code -> id
  const [wLoading, setWLoading] = useState(false);

  const fetchPredictions = (signal: '' | '매수' | '매도' | '관망') => {
    setLoading(true);
    stockApi.getPredictions(signal || undefined, 100)
      .then((res) => setItems(res.data))
      .finally(() => setLoading(false));
  };

  const fetchWatchlist = useCallback(() => {
    setWLoading(true);
    watchlistApi.get()
      .then((res) => {
        setWatchlist(res.data);
        const map: Record<string, string> = {};
        res.data.forEach((w) => { map[w.stock_code] = w.id; });
        setWatchIds(map);
      })
      .finally(() => setWLoading(false));
  }, []);

  useEffect(() => { fetchPredictions(''); }, []);
  useEffect(() => { fetchWatchlist(); }, [fetchWatchlist]);

  const handleFilter = (s: '' | '매수' | '매도' | '관망') => {
    setFilter(s);
    fetchPredictions(s);
  };

  const toggleWatch = async (e: React.MouseEvent, item: AIPredictionItem) => {
    e.stopPropagation();
    const id = watchIds[item.stock_code];
    if (id) {
      await watchlistApi.remove(id);
      setWatchIds((prev) => { const n = { ...prev }; delete n[item.stock_code]; return n; });
      setWatchlist((prev) => prev.filter((w) => w.stock_code !== item.stock_code));
      if (item.stock_code === selectedCode) onWatchChange?.(item.stock_code, null);
    } else {
      const res = await watchlistApi.add(item.stock_code, item.stock_name);
      setWatchIds((prev) => ({ ...prev, [item.stock_code]: res.data.id }));
      setWatchlist((prev) => [res.data, ...prev]);
      if (item.stock_code === selectedCode) onWatchChange?.(item.stock_code, res.data.id);
    }
  };

  const removeWatch = async (e: React.MouseEvent, w: WatchlistItem) => {
    e.stopPropagation();
    await watchlistApi.remove(w.id);
    setWatchIds((prev) => { const n = { ...prev }; delete n[w.stock_code]; return n; });
    setWatchlist((prev) => prev.filter((x) => x.stock_code !== w.stock_code));
    if (w.stock_code === selectedCode) onWatchChange?.(w.stock_code, null);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 탭 */}
      <div style={{ display: 'flex', borderBottom: '1px solid #1e1e2e', flexShrink: 0 }}>
        {(['ai', 'watchlist'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            style={{
              flex: 1, padding: '7px 0', fontSize: 11, border: 'none', cursor: 'pointer',
              background: 'transparent',
              color: tab === t ? '#a5b4fc' : '#555',
              fontWeight: tab === t ? 600 : 400,
              borderBottom: tab === t ? '2px solid #6366f1' : '2px solid transparent',
            }}>
            {t === 'ai' ? 'AI 예측' : '관심종목'}
          </button>
        ))}
      </div>

      {/* AI 예측 탭 */}
      {tab === 'ai' && (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          <UpdateNotice />
          <div style={{ display: 'flex', gap: 4, padding: '6px 8px', borderBottom: '1px solid #1e1e2e', flexWrap: 'wrap' }}>
            {(['', '매수', '매도', '관망'] as const).map((s) => (
              <button key={s} onClick={() => handleFilter(s)}
                style={{
                  padding: '2px 7px', fontSize: 10, borderRadius: 4, border: 'none', cursor: 'pointer',
                  background: filter === s ? '#6366f1' : '#1e1e2e',
                  color: filter === s ? '#fff' : '#888',
                }}>
                {s || '전체'}
              </button>
            ))}
          </div>
          {loading ? (
            <div style={{ padding: 10, fontSize: 11, color: '#666' }}>불러오는 중...</div>
          ) : (
            <div style={{ overflowY: 'auto', flex: 1 }}>
              {items.map((item) => {
                const isActive = selectedCode === item.stock_code;
                const isWatching = !!watchIds[item.stock_code];
                return (
                  <div key={item.stock_code}
                    onClick={() => onSelectStock(item.stock_code, item.stock_name)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6,
                      padding: '5px 8px', cursor: 'pointer', borderBottom: '1px solid #13131e',
                      background: isActive ? '#1a1a30' : 'transparent',
                    }}
                    onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = '#151525'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = isActive ? '#1a1a30' : 'transparent'; }}
                  >
                    <span style={{
                      width: 26, textAlign: 'center', fontSize: 9, padding: '1px 2px', borderRadius: 3, flexShrink: 0,
                      background: SIGNAL_BG[item.signal], color: SIGNAL_COLOR[item.signal], fontWeight: 700,
                    }}>
                      {item.signal}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 11, color: isActive ? '#a5b4fc' : '#d1d5db',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        fontWeight: isActive ? 600 : 400,
                      }}>
                        {item.stock_name}
                      </div>
                      <div style={{ fontSize: 9, color: '#4b5563' }}>
                        {item.stock_code} · {fmtDate(item.predicted_at)}
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 10, color: '#9ca3af' }}>
                          {item.current_price != null ? fmtPrice(item.current_price) : '-'}
                        </div>
                        {item.change_pct != null && (
                          <div style={{ fontSize: 9, color: item.change_pct > 0 ? '#16a34a' : item.change_pct < 0 ? '#dc2626' : '#6b7280' }}>
                            {item.change_pct > 0 ? '+' : ''}{item.change_pct.toFixed(2)}%
                          </div>
                        )}
                      </div>
                      {/* 별표 버튼 */}
                      <button
                        onClick={(e) => toggleWatch(e, item)}
                        title={isWatching ? '관심종목 제거' : '관심종목 추가'}
                        style={{
                          background: 'none', border: 'none', cursor: 'pointer', padding: '2px',
                          fontSize: 13, color: isWatching ? '#fbbf24' : '#374151',
                          lineHeight: 1,
                        }}>
                        {isWatching ? '★' : '☆'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* 관심종목 탭 */}
      {tab === 'watchlist' && (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          {wLoading ? (
            <div style={{ padding: 10, fontSize: 11, color: '#666' }}>불러오는 중...</div>
          ) : watchlist.length === 0 ? (
            <div style={{ padding: 20, fontSize: 11, color: '#4b5563', textAlign: 'center', marginTop: 20 }}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>☆</div>
              AI 예측 목록에서 ★ 눌러<br />관심종목을 추가하세요
            </div>
          ) : (
            <div style={{ overflowY: 'auto', flex: 1 }}>
              {watchlist.map((w) => {
                const isActive = selectedCode === w.stock_code;
                return (
                  <div key={w.id}
                    onClick={() => onSelectStock(w.stock_code, w.stock_name)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6,
                      padding: '6px 10px', cursor: 'pointer', borderBottom: '1px solid #13131e',
                      background: isActive ? '#1a1a30' : 'transparent',
                    }}
                    onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = '#151525'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = isActive ? '#1a1a30' : 'transparent'; }}
                  >
                    {w.signal && (
                      <span style={{
                        width: 26, textAlign: 'center', fontSize: 9, padding: '1px 2px', borderRadius: 3, flexShrink: 0,
                        background: SIGNAL_BG[w.signal] ?? '#1e1e2e', color: SIGNAL_COLOR[w.signal] ?? '#aaa', fontWeight: 700,
                      }}>
                        {w.signal}
                      </span>
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 11, color: isActive ? '#a5b4fc' : '#d1d5db',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        fontWeight: isActive ? 600 : 400,
                      }}>
                        {w.stock_name}
                      </div>
                      <div style={{ fontSize: 9, color: '#4b5563' }}>{w.stock_code}</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                      {w.current_price != null && (
                        <div style={{ fontSize: 10, color: '#9ca3af' }}>{fmtPrice(w.current_price)}</div>
                      )}
                      <button
                        onClick={(e) => removeWatch(e, w)}
                        title="관심종목 제거"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', fontSize: 13, color: '#fbbf24', lineHeight: 1 }}>
                        ★
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RightPanel;
