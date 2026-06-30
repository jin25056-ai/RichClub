import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { marketApi, PerformanceResponse, SimulationResponse, SimYearResult, HoldingItem, TradeRecord } from '../api/stock';
import { useModel } from '../contexts/ModelContext';

const pctColor = (v: number) => v >= 0 ? '#16a34a' : '#dc2626';
const pctStr = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
const fmtKRW = (n: number) => {
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 100000000) return `${sign}${(abs / 100000000).toFixed(1)}억`;
  if (abs >= 10000) return `${sign}${(abs / 10000).toFixed(0)}만`;
  return n.toLocaleString();
};
const fmtPrice = (n: number) =>
  n >= 1000000 ? `${(n / 1000000).toFixed(1)}M`
  : n >= 1000 ? `${Math.round(n / 1000)}K`
  : String(Math.round(n));

const PERIODS = ['1m', '3m', '6m', 'all'] as const;
const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: CURRENT_YEAR - 2020 }, (_, i) => CURRENT_YEAR - i);
const MAX_STOCK_OPTIONS = [5, 10, 20, 30, 50];
const PAGE_SIZE = 50;
const MAIN_TABS = [{ key: 'perf', label: 'AI 실적' }, { key: 'sim', label: '시뮬레이션' }];
const ACTIVE_TABS = [{ key: 'trades', label: '매매 기록' }, { key: 'holdings', label: '현재 보유' }];
const SUB_TABS = [{ key: 'bystock', label: '종목별 수익률' }, { key: 'list', label: '전체 목록' }];

type CalcMode = 'sum' | 'avg';

const CALC_MODES: { key: CalcMode; label: string; desc: string }[] = [
  { key: 'sum', label: '합산', desc: '완료된 모든 거래의 수익률을 단순 합산합니다. (+와 - 모두 포함) 예: +10%, -5%, +20% → +25%.' },
  { key: 'avg', label: '평균', desc: '거래 1건당 평균 수익률입니다. 거래 횟수와 무관하게 모델의 실력을 비교할 때 유용합니다.' },
];

function calcCumulative(returns: number[], mode: CalcMode): number {
  if (returns.length === 0) return 0;
  if (mode === 'sum') return parseFloat(returns.reduce((a, b) => a + b, 0).toFixed(2));
  return parseFloat((returns.reduce((a, b) => a + b, 0) / returns.length).toFixed(2));
}

const YearDetailModal: React.FC<{ year: number; modelId: string; onClose: () => void }> = ({ year, modelId, onClose }) => {
  const navigate = useNavigate();
  const [data, setData] = useState<PerformanceResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    marketApi.getPerformance(modelId, undefined, year)
      .then((res) => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [year, modelId]);

  const completed = data?.trades.filter((t) => t.return_pct != null) ?? [];

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 1000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: 60, overflowY: 'auto' }} onClick={onClose}>
      <div style={{ background: '#0f0f1a', border: '1px solid #2d2d3d', borderRadius: 12, width: '92%', maxWidth: 700, padding: '20px', marginBottom: 40 }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0' }}>{year}년 매매 상세</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#6b7280', fontSize: 18, cursor: 'pointer' }}>×</button>
        </div>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#4b5563' }}>불러오는 중...</div>
        ) : !data ? (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#4b5563' }}>데이터 없음</div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 16 }}>
              {[
                { label: '승률', value: `${data.win_rate.toFixed(1)}%`, sub: `${data.win_count}승 ${data.lose_count}패`, color: data.win_rate >= 50 ? '#16a34a' : '#dc2626' },
                { label: '평균 수익률', value: pctStr(data.avg_return_pct), sub: `거래 ${data.total_trades}건`, color: pctColor(data.avg_return_pct) },
                { label: '최고/최저', value: pctStr(data.max_return_pct), sub: `최저 ${pctStr(data.max_loss_pct)}`, color: '#a5b4fc' },
              ].map((item) => (
                <div key={item.label} style={{ background: '#1a1a2e', borderRadius: 8, padding: '10px 12px', textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: '#4b5563', marginBottom: 4 }}>{item.label}</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: item.color }}>{item.value}</div>
                  <div style={{ fontSize: 9, color: '#374151', marginTop: 2 }}>{item.sub}</div>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 10, color: '#4b5563', marginBottom: 8 }}>완료 거래 {completed.length}건</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3, maxHeight: 460, overflowY: 'auto' }}>
              {completed.map((t: TradeRecord, i: number) => (
                <div key={i} onClick={() => { if (t.stock_code) { onClose(); navigate(`/?code=${t.stock_code}`); } }}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderRadius: 7, cursor: t.stock_code ? 'pointer' : 'default', background: (t.return_pct ?? 0) >= 0 ? '#14532d10' : '#7f1d1d10', border: `1px solid ${pctColor(t.return_pct ?? 0)}22` }}
                  onMouseEnter={(e) => { if (t.stock_code) e.currentTarget.style.opacity = '0.75'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}>
                  <div>
                    <div style={{ fontSize: 11, color: '#d1d5db', fontWeight: 500, marginBottom: 3 }}>
                      {t.stock_name}<span style={{ fontSize: 9, color: '#374151', marginLeft: 6 }}>{t.stock_code}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 6, fontSize: 9, color: '#6b7280' }}>
                      <span><span style={{ color: '#16a34a', fontWeight: 600 }}>B</span> {t.buy_date} · {fmtPrice(t.buy_price)}</span>
                      <span style={{ color: '#374151' }}>→</span>
                      <span><span style={{ color: '#dc2626', fontWeight: 600 }}>S</span> {t.sell_date} · {fmtPrice(t.sell_price ?? 0)}</span>
                    </div>
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: pctColor(t.return_pct ?? 0), flexShrink: 0, marginLeft: 12 }}>{pctStr(t.return_pct ?? 0)}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

const PerformancePage: React.FC = () => {
  const navigate = useNavigate();
  const { models, selectedModel, setSelectedModel } = useModel();

  const [perfData, setPerfData] = useState<PerformanceResponse | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);
  const [period, setPeriod] = useState<string>('6m');
  const [perfYear, setPerfYear] = useState<number | undefined>(undefined);
  const [activeTab, setActiveTab] = useState<string>('trades');
  const [subTab, setSubTab] = useState<string>('bystock');
  const [calcMode, setCalcMode] = useState<CalcMode>('sum');
  const [showModeInfo, setShowModeInfo] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [tradePage, setTradePage] = useState(1);
  const [mainTab, setMainTab] = useState<string>('perf');
  const [simData, setSimData] = useState<SimulationResponse | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [principal, setPrincipal] = useState('10000000');
  const [maxStocks, setMaxStocks] = useState(10);
  const [simYear, setSimYear] = useState<number | undefined>(undefined);
  const [detailYear, setDetailYear] = useState<number | null>(null);

  const fetchPerf = (modelId: string, p: string, y?: number) => {
    setPerfLoading(true);
    marketApi.getPerformance(modelId, p, y)
      .then((res) => setPerfData(res.data))
      .catch(() => setPerfData(null))
      .finally(() => setPerfLoading(false));
  };

  const fetchSim = (modelId: string, prin: number, ms: number, y?: number) => {
    setSimLoading(true);
    marketApi.getSimulation(modelId, prin, ms, y)
      .then((res) => setSimData(res.data))
      .catch(() => setSimData(null))
      .finally(() => setSimLoading(false));
  };

  useEffect(() => {
    if (!localStorage.getItem('access_token')) { navigate('/auth'); return; }
    fetchPerf(selectedModel, period, perfYear);
  }, [selectedModel, period, perfYear]);

  const handleHoldingClick = (code: string, name: string) => {
    setSearchQuery(name);
    setActiveTab('trades');
    setSubTab('list');
    setTradePage(1);
  };

  const completedTrades = perfData?.trades.filter((t) => t.return_pct != null) ?? [];

  const byStock = useMemo(() => {
    const map: Record<string, { name: string; code: string; returns: number[]; win: number; lose: number }> = {};
    for (const t of completedTrades) {
      const code = t.stock_code ?? '';
      if (!map[code]) map[code] = { name: t.stock_name ?? '', code, returns: [], win: 0, lose: 0 };
      map[code].returns.push(t.return_pct as number);
      if ((t.return_pct as number) > 0) map[code].win++;
      else map[code].lose++;
    }
    return Object.values(map)
      .map((s) => ({
        ...s,
        count: s.returns.length,
        avg: parseFloat((s.returns.reduce((a, b) => a + b, 0) / s.returns.length).toFixed(2)),
        total: parseFloat(s.returns.reduce((a, b) => a + b, 0).toFixed(2)),
        winRate: parseFloat((s.win / s.returns.length * 100).toFixed(1)),
      }))
      .sort((a, b) => b.avg - a.avg);
  }, [completedTrades]);

  const q = searchQuery.trim().toLowerCase();
  const filteredTrades = q
    ? completedTrades.filter((t) => t.stock_name?.toLowerCase().includes(q) || t.stock_code?.includes(q))
    : completedTrades;
  const isFiltered = q.length > 0;
  const totalPages = isFiltered ? 1 : Math.ceil(filteredTrades.length / PAGE_SIZE);
  const pagedTrades = isFiltered
    ? filteredTrades
    : filteredTrades.slice((tradePage - 1) * PAGE_SIZE, tradePage * PAGE_SIZE);

  const completedReturns = completedTrades.map((t) => t.return_pct as number);
  const displayCumulative = calcCumulative(completedReturns, calcMode);
  const currentModeInfo = CALC_MODES.find((m) => m.key === calcMode)!;
  const principalNum = parseFloat(principal.replace(/,/g, '')) || 0;

  return (
    <div style={{ background: '#0a0a14', minHeight: '100vh', fontFamily: 'inherit', color: '#e2e8f0' }}>
      {detailYear !== null && (
        <YearDetailModal year={detailYear} modelId={selectedModel} onClose={() => setDetailYear(null)} />
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 20px', borderBottom: '1px solid #1e1e2e', flexWrap: 'wrap' }}>
        <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', color: '#6b7280', fontSize: 18, cursor: 'pointer', lineHeight: 1 }}>&#8592;</button>
        <span style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0' }}>AI 실적</span>
        <div style={{ display: 'flex', gap: 4 }}>
          {models.map((m) => (
            <button key={m.id} onClick={() => { if (m.available) setSelectedModel(m.id); }} disabled={!m.available}
              style={{ padding: '3px 10px', fontSize: 10, borderRadius: 4, border: 'none', cursor: m.available ? 'pointer' : 'default', background: selectedModel === m.id ? '#6366f1' : '#1e1e2e', color: selectedModel === m.id ? '#fff' : m.available ? '#9ca3af' : '#374151' }}>
              {m.name}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 0, marginLeft: 8, background: '#1e1e2e', borderRadius: 6, overflow: 'hidden' }}>
          {MAIN_TABS.map(({ key, label }) => (
            <button key={key} onClick={() => setMainTab(key)}
              style={{ padding: '4px 12px', fontSize: 10, border: 'none', cursor: 'pointer', background: mainTab === key ? '#6366f1' : 'transparent', color: mainTab === key ? '#fff' : '#6b7280' }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ padding: '16px 20px', maxWidth: 1000, margin: '0 auto' }}>

        {mainTab === 'perf' && (
          <>
            <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontSize: 10, color: '#4b5563' }}>기간</span>
              {PERIODS.map((p) => (
                <button key={p} onClick={() => { setPeriod(p); setPerfYear(undefined); setSearchQuery(''); setTradePage(1); }}
                  style={{ padding: '3px 8px', fontSize: 10, borderRadius: 4, border: 'none', cursor: 'pointer', background: period === p && !perfYear ? '#6366f1' : '#1e1e2e', color: period === p && !perfYear ? '#fff' : '#555' }}>
                  {p}
                </button>
              ))}
              <span style={{ fontSize: 10, color: '#4b5563', marginLeft: 8 }}>연도</span>
              {YEARS.map((y) => (
                <button key={y} onClick={() => { setPerfYear(y); setSearchQuery(''); setTradePage(1); }}
                  style={{ padding: '3px 8px', fontSize: 10, borderRadius: 4, border: 'none', cursor: 'pointer', background: perfYear === y ? '#6366f1' : '#1e1e2e', color: perfYear === y ? '#fff' : '#555' }}>
                  {y}
                </button>
              ))}
            </div>

            {perfLoading ? (
              <div style={{ textAlign: 'center', padding: '60px 0', color: '#4b5563' }}>불러오는 중...</div>
            ) : !perfData ? (
              <div style={{ textAlign: 'center', padding: '60px 0', color: '#4b5563' }}>데이터 없음</div>
            ) : (
              <>
                <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: '10px 14px', marginBottom: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 10, color: '#4b5563', flexShrink: 0 }}>수익률 기준</span>
                    <div style={{ display: 'flex', gap: 4 }}>
                      {CALC_MODES.map((m) => (
                        <button key={m.key} onClick={() => setCalcMode(m.key)}
                          style={{ padding: '3px 10px', fontSize: 10, borderRadius: 4, border: 'none', cursor: 'pointer', background: calcMode === m.key ? '#6366f1' : '#1e1e2e', color: calcMode === m.key ? '#fff' : '#6b7280' }}>
                          {m.label}
                        </button>
                      ))}
                    </div>
                    <button onClick={() => setShowModeInfo((v) => !v)}
                      style={{ fontSize: 9, color: '#4b5563', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', flexShrink: 0 }}>
                      {showModeInfo ? '설명 닫기' : '기준 설명 보기'}
                    </button>
                  </div>
                  {showModeInfo && (
                    <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {CALC_MODES.map((m) => (
                        <div key={m.key} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                          <span style={{ fontSize: 9, fontWeight: 700, color: calcMode === m.key ? '#a5b4fc' : '#4b5563', flexShrink: 0, width: 32 }}>{m.label}</span>
                          <span style={{ fontSize: 9, color: '#6b7280', lineHeight: 1.6 }}>{m.desc}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 14 }}>
                  {[
                    { label: '승률', value: `${perfData.win_rate.toFixed(1)}%`, sub: `${perfData.win_count}승 ${perfData.lose_count}패`, color: perfData.win_rate >= 50 ? '#16a34a' : '#dc2626' },
                    { label: `수익률 (${currentModeInfo.label})`, value: pctStr(displayCumulative), sub: `완료 거래 ${completedReturns.length}건 기준`, color: pctColor(displayCumulative) },
                    { label: '거래 횟수', value: `${perfData.total_trades}건`, sub: `최고 ${pctStr(perfData.max_return_pct)} / 최저 ${pctStr(perfData.max_loss_pct)}`, color: '#a5b4fc' },
                  ].map((item) => (
                    <div key={item.label} style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, padding: '14px 16px', textAlign: 'center' }}>
                      <div style={{ fontSize: 10, color: '#4b5563', marginBottom: 6 }}>{item.label}</div>
                      <div style={{ fontSize: 26, fontWeight: 700, color: item.color }}>{item.value}</div>
                      <div style={{ fontSize: 9, color: '#374151', marginTop: 4 }}>{item.sub}</div>
                    </div>
                  ))}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', borderBottom: '1px solid #1e1e2e', marginBottom: 12 }}>
                  {ACTIVE_TABS.map(({ key, label }) => {
                    const count = key === 'trades' ? completedTrades.length : perfData.holdings.length;
                    return (
                      <button key={key} onClick={() => { setActiveTab(key); if (key === 'trades') setSearchQuery(''); setTradePage(1); }}
                        style={{ padding: '8px 16px', fontSize: 11, border: 'none', cursor: 'pointer', background: 'transparent', color: activeTab === key ? '#a5b4fc' : '#555', fontWeight: activeTab === key ? 600 : 400, borderBottom: activeTab === key ? '2px solid #6366f1' : '2px solid transparent' }}>
                        {label} ({count})
                      </button>
                    );
                  })}
                </div>

                {activeTab === 'trades' && (
                  <>
                    <div style={{ display: 'flex', gap: 0, marginBottom: 12, background: '#1e1e2e', borderRadius: 6, overflow: 'hidden', width: 'fit-content' }}>
                      {SUB_TABS.map(({ key, label }) => (
                        <button key={key} onClick={() => { setSubTab(key); setSearchQuery(''); setTradePage(1); }}
                          style={{ padding: '5px 14px', fontSize: 10, border: 'none', cursor: 'pointer', background: subTab === key ? '#6366f1' : 'transparent', color: subTab === key ? '#fff' : '#6b7280' }}>
                          {label}
                        </button>
                      ))}
                    </div>

                    {subTab === 'bystock' && (
                      <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, overflow: 'hidden' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 60px 60px 80px 80px', padding: '8px 14px', borderBottom: '1px solid #1e1e2e', fontSize: 9, color: '#4b5563', fontWeight: 600 }}>
                          <span>종목</span>
                          <span style={{ textAlign: 'center' }}>거래</span>
                          <span style={{ textAlign: 'center' }}>승률</span>
                          <span style={{ textAlign: 'center' }}>평균수익</span>
                          <span style={{ textAlign: 'right' }}>합산수익</span>
                        </div>
                        {byStock.map((s) => (
                          <div key={s.code}
                            onClick={() => { setSearchQuery(s.name); setSubTab('list'); setTradePage(1); }}
                            style={{ display: 'grid', gridTemplateColumns: '1fr 60px 60px 80px 80px', padding: '9px 14px', borderBottom: '1px solid #13131e', fontSize: 11, alignItems: 'center', cursor: 'pointer' }}
                            onMouseEnter={(e) => (e.currentTarget.style.background = '#1a1a2e')}
                            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                            <div>
                              <div style={{ fontSize: 11, color: '#d1d5db', fontWeight: 500 }}>{s.name}</div>
                              <div style={{ fontSize: 9, color: '#374151' }}>{s.code}</div>
                            </div>
                            <span style={{ textAlign: 'center', color: '#6b7280' }}>{s.count}건</span>
                            <span style={{ textAlign: 'center', color: s.winRate >= 50 ? '#16a34a' : '#dc2626' }}>{s.winRate}%</span>
                            <span style={{ textAlign: 'center', color: pctColor(s.avg) }}>{pctStr(s.avg)}</span>
                            <span style={{ textAlign: 'right', color: pctColor(s.total) }}>{pctStr(s.total)}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {subTab === 'list' && (
                      <>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 10 }}>
                          <input
                            placeholder="종목명 또는 코드로 검색"
                            value={searchQuery}
                            onChange={(e) => { setSearchQuery(e.target.value); setTradePage(1); }}
                            style={{ flex: 1, background: '#1e1e2e', border: '1px solid #2d2d3d', borderRadius: 6, padding: '7px 12px', fontSize: 11, color: '#e2e8f0', outline: 'none' }}
                          />
                          {searchQuery && (
                            <button onClick={() => { setSearchQuery(''); setTradePage(1); }}
                              style={{ fontSize: 10, padding: '6px 12px', borderRadius: 6, border: '1px solid #2d2d3d', background: '#1e1e2e', color: '#9ca3af', cursor: 'pointer', flexShrink: 0 }}>
                              초기화
                            </button>
                          )}
                        </div>
                        {isFiltered && (
                          <div style={{ fontSize: 9, color: '#6366f1', marginBottom: 8 }}>
                            "{searchQuery}" 검색 결과 {filteredTrades.length}건 (전체 {completedTrades.length}건)
                          </div>
                        )}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                          {filteredTrades.length === 0 ? (
                            <div style={{ textAlign: 'center', padding: '30px 0', color: '#4b5563', fontSize: 12 }}>
                              {isFiltered ? `"${searchQuery}"에 해당하는 매매 기록이 없습니다` : '매매 기록 없음'}
                            </div>
                          ) : pagedTrades.map((t: TradeRecord, i: number) => (
                            <div key={i} onClick={() => { if (t.stock_code) navigate(`/?code=${t.stock_code}`); }}
                              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', borderRadius: 8, cursor: t.stock_code ? 'pointer' : 'default', background: (t.return_pct ?? 0) >= 0 ? '#14532d12' : '#7f1d1d12', border: `1px solid ${pctColor(t.return_pct ?? 0)}22` }}
                              onMouseEnter={(e) => { if (t.stock_code) e.currentTarget.style.opacity = '0.8'; }}
                              onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}>
                              <div>
                                <div style={{ fontSize: 12, color: '#d1d5db', fontWeight: 500, marginBottom: 4 }}>
                                  {t.stock_name}<span style={{ fontSize: 9, color: '#4b5563', marginLeft: 6 }}>{t.stock_code}</span>
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
                        {!isFiltered && totalPages > 1 && (
                          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 6, marginTop: 16 }}>
                            <button onClick={() => setTradePage((p) => Math.max(1, p - 1))} disabled={tradePage === 1}
                              style={{ padding: '4px 10px', fontSize: 10, borderRadius: 4, border: '1px solid #2d2d3d', background: '#1e1e2e', color: tradePage === 1 ? '#374151' : '#9ca3af', cursor: tradePage === 1 ? 'default' : 'pointer' }}>
                              이전
                            </button>
                            {Array.from({ length: totalPages }, (_, i) => i + 1)
                              .filter((p) => p === 1 || p === totalPages || Math.abs(p - tradePage) <= 2)
                              .reduce<(number | string)[]>((acc, p, idx, arr) => {
                                if (idx > 0 && (p as number) - (arr[idx - 1] as number) > 1) acc.push('...');
                                acc.push(p);
                                return acc;
                              }, [])
                              .map((p, i) => (
                                typeof p === 'string' ? (
                                  <span key={`e-${i}`} style={{ fontSize: 10, color: '#374151' }}>...</span>
                                ) : (
                                  <button key={p} onClick={() => setTradePage(p)}
                                    style={{ padding: '4px 8px', fontSize: 10, borderRadius: 4, border: '1px solid #2d2d3d', background: tradePage === p ? '#6366f1' : '#1e1e2e', color: tradePage === p ? '#fff' : '#9ca3af', cursor: 'pointer', minWidth: 28 }}>
                                    {p}
                                  </button>
                                )
                              ))}
                            <button onClick={() => setTradePage((p) => Math.min(totalPages, p + 1))} disabled={tradePage === totalPages}
                              style={{ padding: '4px 10px', fontSize: 10, borderRadius: 4, border: '1px solid #2d2d3d', background: '#1e1e2e', color: tradePage === totalPages ? '#374151' : '#9ca3af', cursor: tradePage === totalPages ? 'default' : 'pointer' }}>
                              다음
                            </button>
                            <span style={{ fontSize: 9, color: '#374151' }}>{tradePage}/{totalPages} · 총 {filteredTrades.length}건</span>
                          </div>
                        )}
                      </>
                    )}
                  </>
                )}

                {activeTab === 'holdings' && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 8 }}>
                    {perfData.holdings.length === 0 ? (
                      <div style={{ color: '#4b5563', fontSize: 12, padding: '20px 0' }}>현재 보유 종목 없음</div>
                    ) : perfData.holdings.map((h: HoldingItem) => (
                      <div key={h.stock_code} onClick={() => handleHoldingClick(h.stock_code, h.stock_name)}
                        style={{ background: '#0f0f1a', border: `1px solid ${pctColor(h.unrealized_pct)}22`, borderRadius: 8, padding: '12px 14px', cursor: 'pointer' }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = '#1a1a30')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = '#0f0f1a')}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                          <div>
                            <div style={{ fontSize: 12, fontWeight: 600, color: '#d1d5db' }}>{h.stock_name}</div>
                            <div style={{ fontSize: 9, color: '#4b5563' }}>{h.stock_code}</div>
                          </div>
                          <div style={{ fontSize: 18, fontWeight: 700, color: pctColor(h.unrealized_pct) }}>{pctStr(h.unrealized_pct)}</div>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#6b7280' }}>
                          <span>매수 {h.buy_date} · {fmtPrice(h.buy_price)}</span>
                          <span>현재 {fmtPrice(h.current_price)}</span>
                        </div>
                        <div style={{ marginTop: 5, fontSize: 9, color: '#374151' }}>탭하면 매매기록 보기</div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        )}

        {mainTab === 'sim' && (
          <>
            <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, padding: '16px 20px', marginBottom: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', marginBottom: 12 }}>시뮬레이션 설정</div>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div>
                  <div style={{ fontSize: 9, color: '#4b5563', marginBottom: 5 }}>투자 원금</div>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    <input value={principal} onChange={(e) => setPrincipal(e.target.value.replace(/[^0-9]/g, ''))}
                      style={{ width: 120, background: '#1e1e2e', border: '1px solid #2d2d3d', borderRadius: 6, padding: '6px 10px', fontSize: 12, color: '#e2e8f0', outline: 'none' }} />
                    <span style={{ fontSize: 10, color: '#555' }}>원</span>
                  </div>
                  <div style={{ display: 'flex', gap: 3, marginTop: 5 }}>
                    {[[100, '100만'], [500, '500만'], [1000, '1000만'], [5000, '5000만']].map(([w, label]) => (
                      <button key={w} onClick={() => setPrincipal(String(Number(w) * 10000))}
                        style={{ fontSize: 9, padding: '2px 6px', borderRadius: 3, border: 'none', cursor: 'pointer', background: '#1e1e2e', color: '#888' }}>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 9, color: '#4b5563', marginBottom: 5 }}>동시 보유 종목 수</div>
                  <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
                    {MAX_STOCK_OPTIONS.map((n) => (
                      <button key={n} onClick={() => setMaxStocks(n)}
                        style={{ padding: '5px 10px', fontSize: 10, borderRadius: 4, border: 'none', cursor: 'pointer', background: maxStocks === n ? '#6366f1' : '#1e1e2e', color: maxStocks === n ? '#fff' : '#666' }}>
                        {n}종목
                      </button>
                    ))}
                    <input type="number" min={1} max={200} value={maxStocks}
                      onChange={(e) => { const v = parseInt(e.target.value, 10); if (!isNaN(v) && v > 0) setMaxStocks(v); }}
                      style={{ width: 56, background: '#1e1e2e', border: '1px solid #2d2d3d', borderRadius: 4, padding: '5px 6px', fontSize: 10, color: '#e2e8f0', outline: 'none' }} />
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 9, color: '#4b5563', marginBottom: 5 }}>연도 (전체면 비움)</div>
                  <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                    <button onClick={() => setSimYear(undefined)}
                      style={{ padding: '5px 10px', fontSize: 10, borderRadius: 4, border: 'none', cursor: 'pointer', background: !simYear ? '#6366f1' : '#1e1e2e', color: !simYear ? '#fff' : '#666' }}>
                      전체
                    </button>
                    {YEARS.map((y) => (
                      <button key={y} onClick={() => setSimYear(y)}
                        style={{ padding: '5px 10px', fontSize: 10, borderRadius: 4, border: 'none', cursor: 'pointer', background: simYear === y ? '#6366f1' : '#1e1e2e', color: simYear === y ? '#fff' : '#666' }}>
                        {y}
                      </button>
                    ))}
                  </div>
                </div>
                <button onClick={() => fetchSim(selectedModel, principalNum, maxStocks, simYear)} disabled={principalNum <= 0}
                  style={{ padding: '8px 20px', fontSize: 11, borderRadius: 6, border: 'none', cursor: principalNum > 0 ? 'pointer' : 'default', background: principalNum > 0 ? '#6366f1' : '#374151', color: '#fff', fontWeight: 600, flexShrink: 0 }}>
                  시뮬레이션 실행
                </button>
              </div>
              <div style={{ marginTop: 10, fontSize: 9, color: '#374151', lineHeight: 1.6 }}>
                투자금을 동시 보유 종목 수로 균등 분배하여 AI 매수 신호마다 진입, 매도 신호에 청산하는 방식으로 계산합니다. 동시 보유 한도 초과 시 신규 매수는 건너뜁니다.
              </div>
            </div>

            {simLoading ? (
              <div style={{ textAlign: 'center', padding: '60px 0', color: '#4b5563' }}>계산 중...</div>
            ) : simData ? (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 14 }}>
                  {[
                    { label: '원금', value: `${fmtKRW(simData.principal)}원`, color: '#9ca3af', sub: '' },
                    { label: '총 수익', value: `${simData.total_profit >= 0 ? '+' : ''}${fmtKRW(simData.total_profit)}원`, color: pctColor(simData.total_profit), sub: pctStr(simData.total_return_pct) },
                    { label: '최종 금액', value: `${fmtKRW(simData.total_final_amount)}원`, color: pctColor(simData.total_return_pct), sub: '' },
                  ].map((item) => (
                    <div key={item.label} style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, padding: '14px 16px', textAlign: 'center' }}>
                      <div style={{ fontSize: 10, color: '#4b5563', marginBottom: 6 }}>{item.label}</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: item.color }}>{item.value}</div>
                      {item.sub && <div style={{ fontSize: 10, color: item.color, marginTop: 4 }}>{item.sub}</div>}
                    </div>
                  ))}
                </div>
                <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, overflow: 'hidden' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '70px 1fr 1fr 1fr 1fr 1fr 80px', padding: '10px 16px', borderBottom: '1px solid #1e1e2e', fontSize: 9, color: '#4b5563', fontWeight: 600 }}>
                    <span>연도</span>
                    <span style={{ textAlign: 'center' }}>거래</span>
                    <span style={{ textAlign: 'center' }}>승률</span>
                    <span style={{ textAlign: 'center' }}>평균수익</span>
                    <span style={{ textAlign: 'center' }}>수익</span>
                    <span style={{ textAlign: 'right' }}>잔액</span>
                    <span></span>
                  </div>
                  {simData.years.map((yr: SimYearResult) => (
                    <div key={yr.year} style={{ display: 'grid', gridTemplateColumns: '70px 1fr 1fr 1fr 1fr 1fr 80px', padding: '10px 16px', borderBottom: '1px solid #13131e', fontSize: 11, alignItems: 'center' }}>
                      <span style={{ color: '#a5b4fc', fontWeight: 600 }}>{yr.year}</span>
                      <span style={{ textAlign: 'center', color: '#6b7280' }}>{yr.total_trades}건</span>
                      <span style={{ textAlign: 'center', color: yr.win_rate >= 50 ? '#16a34a' : '#dc2626' }}>{yr.win_rate.toFixed(1)}%</span>
                      <span style={{ textAlign: 'center', color: pctColor(yr.avg_return_pct) }}>{pctStr(yr.avg_return_pct)}</span>
                      <span style={{ textAlign: 'center', color: pctColor(yr.profit) }}>{yr.profit >= 0 ? '+' : ''}{fmtKRW(yr.profit)}</span>
                      <span style={{ textAlign: 'right', color: '#d1d5db', fontWeight: 500 }}>{fmtKRW(yr.final_amount)}원</span>
                      <span style={{ textAlign: 'right' }}>
                        <button onClick={() => setDetailYear(yr.year)}
                          style={{ fontSize: 9, padding: '3px 8px', borderRadius: 4, border: '1px solid #2d2d3d', background: '#1e1e2e', color: '#9ca3af', cursor: 'pointer' }}>
                          상세보기
                        </button>
                      </span>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 8, fontSize: 9, color: '#374151', textAlign: 'right' }}>
                  종목당 투자금 {fmtKRW(principalNum / maxStocks)}원 · 동시 최대 {simData.max_stocks}종목
                </div>
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: '40px 0', color: '#374151', fontSize: 12 }}>
                설정 후 시뮬레이션 실행 버튼을 눌러주세요
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default PerformancePage;
