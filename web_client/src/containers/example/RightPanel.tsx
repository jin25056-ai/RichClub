import React, { useState, useEffect, useCallback } from 'react';
import { stockApi, marketApi, watchlistApi, AIPredictionItem, WatchlistItem, RecommendItem } from '../../api/stock';

type RightTab = 'ai' | 'recommend' | 'indicator' | 'watchlist' | 'news';

const SIGNAL_COLOR: Record<string, string> = { 매수: '#16a34a', 매도: '#dc2626', 관망: '#d97706', '매수 우세': '#4ade80', '매도 우세': '#f87171', 중립: '#6b7280' };
const SIGNAL_BG: Record<string, string>    = { 매수: '#14532d', 매도: '#7f1d1d', 관망: '#78350f', '매수 우세': '#14532d', '매도 우세': '#7f1d1d', 중립: '#1e1e2e' };

interface Props {
  onSelectStock: (stockCode: string, stockName: string) => void;
  selectedCode?: string;
  onWatchChange?: (code: string, id: string | null) => void;
  modelId?: string;
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

const RightPanel: React.FC<Props> = ({ onSelectStock, selectedCode, onWatchChange, modelId = 'ju-model-v2' }) => {
  const [tab, setTab] = useState<RightTab>('ai');

  type TodaySignalItem = {
    stock_code: string; stock_name: string;
    signal: string; sub: string;
    tags: { label: string; color: string }[];
    close: number | null; rsi: number | null;
    ma_align: string; macd_bull: boolean | null;
  };
  const [indItems, setIndItems] = useState<TodaySignalItem[]>([]);
  const [indDays, setIndDays] = useState(1);
  const [indLoading, setIndLoading] = useState(false);

  const [items, setItems] = useState<AIPredictionItem[]>([]);
  const [filter, setFilter] = useState<'' | '매수' | '매도' | '관망'>('');
  const [loading, setLoading] = useState(false);

  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [watchIds, setWatchIds] = useState<Record<string, string>>({});
  const [wLoading, setWLoading] = useState(false);

  const [recItems, setRecItems] = useState<RecommendItem[]>([]);
  const [recLoading, setRecLoading] = useState(false);
  const [recDate, setRecDate] = useState<string>('');

  const fetchPredictions = (signal: '' | '매수' | '매도' | '관망') => {
    setLoading(true);
    stockApi.getPredictions(signal || undefined, 100, modelId)
      .then((res) => setItems(res.data))
      .finally(() => setLoading(false));
  };

  const fetchWatchlist = useCallback(() => {
    setWLoading(true);
    watchlistApi.get()
      .then((res) => {
        setWatchlist(res.data);
        const map: Record<string, string> = {};
        res.data.forEach((w: WatchlistItem) => { map[w.stock_code] = w.id; });
        setWatchIds(map);
      })
      .finally(() => setWLoading(false));
  }, []);

  const fetchIndicators = useCallback((days: number) => {
    setIndLoading(true);
    stockApi.getTodaySignals(days, 'ju-model-v2')
      .then((res) => setIndItems(res.data))
      .finally(() => setIndLoading(false));
  }, []);

  const fetchRecommend = useCallback(() => {
    setRecLoading(true);
    marketApi.getRecommend()
      .then((res) => { setRecItems(res.data.items); setRecDate(res.data.date); })
      .catch(() => {})
      .finally(() => setRecLoading(false));
  }, []);

  type NewsItem = { title: string; originallink: string; link: string; description: string; pubDate: string; };
  const [newsItems, setNewsItems] = useState<NewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsQuery, setNewsQuery] = useState('주식 증권');

  const fetchNews = useCallback((q?: string) => {
    const query = q ?? '주식 증권';
    setNewsQuery(query);
    setNewsLoading(true);
    stockApi.getNews(query)
      .then((res) => setNewsItems(res.data.items ?? []))
      .finally(() => setNewsLoading(false));
  }, []);

  useEffect(() => { fetchPredictions(''); }, []);
  useEffect(() => { fetchWatchlist(); }, [fetchWatchlist]);
  useEffect(() => { fetchIndicators(indDays); }, []);

  const handleFilter = (s: '' | '매수' | '매도' | '관망') => {
    setFilter(s);
    fetchPredictions(s);
  };

  const handleTabChange = (t: RightTab) => {
    setTab(t);
    if (t === 'news' && newsItems.length === 0) fetchNews();
    if (t === 'recommend' && recItems.length === 0) fetchRecommend();
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
      <div style={{ display: 'flex', borderBottom: '1px solid #1e1e2e', flexShrink: 0 }}>
        {(['ai', 'recommend', 'indicator', 'watchlist', 'news'] as RightTab[]).map((t) => (
          <button key={t} onClick={() => handleTabChange(t)}
            style={{
              flex: 1, padding: '7px 0', fontSize: 10, border: 'none', cursor: 'pointer',
              background: 'transparent',
              color: tab === t ? '#a5b4fc' : '#555',
              fontWeight: tab === t ? 600 : 400,
              borderBottom: tab === t ? '2px solid #6366f1' : '2px solid transparent',
            }}>
            {t === 'ai' ? 'AI' : t === 'recommend' ? '추천' : t === 'indicator' ? '지표' : t === 'watchlist' ? '관심' : '뉴스'}
          </button>
        ))}
      </div>

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
                      <button onClick={(e) => toggleWatch(e, item)} title={isWatching ? '관심종목 제거' : '관심종목 추가'}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', fontSize: 13, color: isWatching ? '#fbbf24' : '#374151', lineHeight: 1 }}>
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

      {tab === 'recommend' && (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          <div style={{ display: 'flex', gap: 4, padding: '6px 8px', borderBottom: '1px solid #1e1e2e', alignItems: 'center', flexShrink: 0 }}>
            <span style={{ fontSize: 9, color: '#4b5563', flex: 1 }}>KOSPI200 + KOSDAQ150 · seo-model-v2 · {recDate}</span>
            <button onClick={fetchRecommend}
              style={{ fontSize: 9, padding: '2px 5px', borderRadius: 3, border: '1px solid #2d2d3d', background: 'transparent', color: '#555', cursor: 'pointer' }}>
              갱신
            </button>
          </div>
          {recLoading ? (
            <div style={{ padding: 20, fontSize: 11, color: '#666', textAlign: 'center' }}>불러오는 중...</div>
          ) : recItems.length === 0 ? (
            <div style={{ padding: 20, fontSize: 11, color: '#4b5563', textAlign: 'center', marginTop: 20 }}>
              추천 종목이 없습니다.
            </div>
          ) : (
            <div style={{ overflowY: 'auto', flex: 1 }}>
              {recItems.map((item, i) => {
                const isActive = selectedCode === item.stock_code;
                const isReg = item.model_name === 'lgb_regressor';
                return (
                  <div key={`${item.stock_code}-${i}`}
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
                      width: 28, textAlign: 'center', fontSize: 8, padding: '1px 2px', borderRadius: 3, flexShrink: 0,
                      background: isReg ? '#1e3a5f' : '#14532d', color: isReg ? '#93c5fd' : '#4ade80', fontWeight: 700,
                    }}>
                      {isReg ? 'REG' : 'CLF'}
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
                        {item.stock_code} · score {item.pred_score.toFixed(4)}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <div style={{ fontSize: 10, color: '#9ca3af' }}>
                        {item.close != null ? fmtPrice(item.close) : '-'}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* 지표 탭 - AI 모델과 무관, ju-model-v2 고정 */}
      {tab === 'indicator' && (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          <div style={{ display: 'flex', gap: 6, padding: '6px 8px', borderBottom: '1px solid #1e1e2e', alignItems: 'center', flexShrink: 0 }}>
            <select value={indDays}
              onChange={(e) => { const d = Number(e.target.value); setIndDays(d); fetchIndicators(d); }}
              style={{ background: '#1e1e2e', border: '1px solid #2d2d3d', borderRadius: 4, color: '#a5b4fc', fontSize: 10, padding: '3px 6px', cursor: 'pointer', outline: 'none' }}>
              <option value={1}>오늘</option>
              <option value={3}>최근 3일</option>
              <option value={7}>최근 7일</option>
            </select>
            <span style={{ fontSize: 9, color: '#374151' }}>{indItems.length}종목</span>
            <button onClick={() => fetchIndicators(indDays)}
              style={{ marginLeft: 'auto', fontSize: 9, padding: '2px 5px', borderRadius: 3, border: '1px solid #2d2d3d', background: 'transparent', color: '#555', cursor: 'pointer' }}>
              갱신
            </button>
          </div>
          {indLoading ? (
            <div style={{ padding: 20, fontSize: 11, color: '#666', textAlign: 'center' }}>불러오는 중...</div>
          ) : (
            <div style={{ overflowY: 'auto', flex: 1 }}>
              {indItems.map((it) => {
                const isActive = selectedCode === it.stock_code;
                const fmtClose = it.close
                  ? it.close >= 1000000 ? `${(it.close/1000000).toFixed(1)}M`
                    : it.close >= 1000 ? `${Math.round(it.close/1000)}K`
                    : String(it.close)
                  : '-';
                return (
                  <div key={it.stock_code}
                    onClick={() => onSelectStock(it.stock_code, it.stock_name)}
                    style={{ padding: '6px 8px', cursor: 'pointer', borderBottom: '1px solid #13131e', background: isActive ? '#1a1a30' : 'transparent' }}
                    onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = '#151525'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = isActive ? '#1a1a30' : 'transparent'; }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 4 }}>
                      <div title={it.signal} style={{
                        flex: 1, fontSize: 11, color: isActive ? '#a5b4fc' : '#d1d5db',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        fontWeight: isActive ? 600 : 400,
                      }}>
                        {it.stock_name}
                      </div>
                      <span style={{ fontSize: 10, color: '#9ca3af', flexShrink: 0 }}>{fmtClose}</span>
                      <button onClick={async (e) => {
                        e.stopPropagation();
                        const id = watchIds[it.stock_code];
                        if (id) {
                          await watchlistApi.remove(id);
                          setWatchIds((prev) => { const n = { ...prev }; delete n[it.stock_code]; return n; });
                          setWatchlist((prev) => prev.filter((w) => w.stock_code !== it.stock_code));
                        } else {
                          const res = await watchlistApi.add(it.stock_code, it.stock_name);
                          setWatchIds((prev) => ({ ...prev, [it.stock_code]: res.data.id }));
                          setWatchlist((prev) => [res.data, ...prev]);
                        }
                      }}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: watchIds[it.stock_code] ? '#fbbf24' : '#374151', padding: 0, lineHeight: 1, flexShrink: 0 }}>
                        {watchIds[it.stock_code] ? '★' : '☆'}
                      </button>
                    </div>
                    <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                      {it.tags.map((tag, ti) => (
                        <span key={ti} style={{
                          fontSize: 8, padding: '1px 4px', borderRadius: 3,
                          background: tag.color + '22', color: tag.color,
                          border: `1px solid ${tag.color}44`,
                          fontWeight: 600, whiteSpace: 'nowrap',
                        }}>
                          {tag.label}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {tab === 'news' && (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          <div style={{ display: 'flex', gap: 4, padding: '6px 8px', borderBottom: '1px solid #1e1e2e', alignItems: 'center', flexShrink: 0 }}>
            <input type="text" value={newsQuery}
              onChange={(e) => setNewsQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') fetchNews(newsQuery); }}
              style={{ flex: 1, padding: '3px 7px', fontSize: 10, minWidth: 0, background: '#1a1a2e', border: '1px solid #2d2d3d', borderRadius: 5, color: newsQuery === '주식 증권' ? '#4b5563' : '#e2e8f0', outline: 'none' }}
            />
            <button onClick={() => fetchNews(newsQuery)}
              style={{ fontSize: 9, padding: '3px 7px', borderRadius: 4, border: '1px solid #2d2d3d', background: 'transparent', color: '#9ca3af', cursor: 'pointer', flexShrink: 0 }}>
              검색
            </button>
            <button onClick={() => { setNewsQuery('주식 증권'); fetchNews('주식 증권'); }}
              style={{ fontSize: 11, padding: '2px 5px', borderRadius: 4, border: '1px solid #2d2d3d', background: 'transparent', color: '#555', cursor: 'pointer', flexShrink: 0 }} title="새로고침">
              ↻
            </button>
          </div>
          {newsLoading ? (
            <div style={{ padding: 20, fontSize: 11, color: '#666', textAlign: 'center' }}>불러오는 중...</div>
          ) : (
            <div style={{ overflowY: 'auto', flex: 1 }}>
              {newsItems.map((item, i) => (
                <a key={i} href={item.originallink || item.link} target="_blank" rel="noreferrer"
                  style={{ display: 'block', padding: '8px 10px', borderBottom: '1px solid #13131e', textDecoration: 'none' }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#151525')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                  <div style={{ fontSize: 11, color: '#d1d5db', fontWeight: 500, marginBottom: 3, lineHeight: 1.4, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
                    dangerouslySetInnerHTML={{ __html: item.title }} />
                  <div style={{ fontSize: 9, color: '#4b5563' }}>
                    {new Date(item.pubDate).toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </div>
                </a>
              ))}
            </div>
          )}
        </div>
      )}

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
                  <div key={w.id} onClick={() => onSelectStock(w.stock_code, w.stock_name)}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', cursor: 'pointer', borderBottom: '1px solid #13131e', background: isActive ? '#1a1a30' : 'transparent' }}
                    onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = '#151525'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = isActive ? '#1a1a30' : 'transparent'; }}
                  >
                    {w.signal && (
                      <span style={{ width: 26, textAlign: 'center', fontSize: 9, padding: '1px 2px', borderRadius: 3, flexShrink: 0, background: SIGNAL_BG[w.signal] ?? '#1e1e2e', color: SIGNAL_COLOR[w.signal] ?? '#aaa', fontWeight: 700 }}>
                        {w.signal}
                      </span>
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 11, color: isActive ? '#a5b4fc' : '#d1d5db', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: isActive ? 600 : 400 }}>
                        {w.stock_name}
                      </div>
                      <div style={{ fontSize: 9, color: '#4b5563' }}>{w.stock_code}</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                      {w.current_price != null && <div style={{ fontSize: 10, color: '#9ca3af' }}>{fmtPrice(w.current_price)}</div>}
                      <button onClick={(e) => removeWatch(e, w)} title="관심종목 제거"
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

      <div style={{ flexShrink: 0, borderTop: '1px solid #1e1e2e', padding: '6px 10px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 8, color: '#6b7280', flexShrink: 0, fontWeight: 600 }}>후원하기</span>
        <div style={{ display: 'flex', gap: 8 }}>
          {[['은행', '-'], ['계좌', '-'], ['예금주', '-']].map(([label, value]) => (
            <div key={label} style={{ display: 'flex', gap: 3, alignItems: 'baseline' }}>
              <span style={{ fontSize: 7, color: '#4b5563' }}>{label}</span>
              <span style={{ fontSize: 9, color: '#9ca3af', fontWeight: 600 }}>{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default RightPanel;
