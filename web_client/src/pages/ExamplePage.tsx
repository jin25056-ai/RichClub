import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import GlobalMarketSection from '../containers/example/GlobalMarketSection';
import RightPanel from '../containers/example/RightPanel';
import TradeModal from '../containers/example/TradeModal';
import StockSearchSection from '../containers/example/StockSearchSection';
import WinRateSection from '../containers/example/WinRateSection';
import { stockApi, watchlistApi } from '../api/stock';
import { getMe, logout } from '../api/auth';
import { User } from '../types';
import { PricingContent } from './PricingPage';
import { useModel } from '../contexts/ModelContext';
import '../styles/example.css';

type Period = '1m' | '3m' | '6m';
type Tab = 'chart' | 'ai' | 'market' | 'winrate';
type ChartInterval = '1d' | '5m';

const isMobile = () => window.innerWidth <= 768;

const PLAN_LABEL: Record<string, { label: string; color: string }> = {
  'basic-plan':  { label: 'Demo',     color: '#6b7280' },
  'ju-model':    { label: 'Basic',    color: '#4ade80' },
  'seo-model':   { label: 'Pro',      color: '#a5b4fc' },
  'auto-trade':  { label: 'Max',      color: '#fb923c' },
  'telegram':    { label: 'Telegram', color: '#38bdf8' },
};

interface ProfileDropdownProps {
  user: User;
  onLogout: () => void;
  onPricingOpen: () => void;
}

const ProfileDropdown: React.FC<ProfileDropdownProps> = ({ user, onLogout, onPricingOpen }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
  };

  const planInfo = PLAN_LABEL[user.plan] ?? PLAN_LABEL['basic-plan'];

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{ fontSize: 10, padding: '3px 8px', background: open ? '#1e1e2e' : 'transparent', color: '#9ca3af', border: '1px solid #2d2d3d', borderRadius: 4, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
      >
        <span style={{ fontSize: 9, color: '#4b5563' }}>&#9679;</span>
        {user.name}
        <span style={{ fontSize: 9, color: planInfo.color, fontWeight: 600, background: planInfo.color + '18', border: `1px solid ${planInfo.color}33`, borderRadius: 3, padding: '1px 5px' }}>{planInfo.label}</span>
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 'calc(100% + 6px)', right: 0, background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 6, padding: '12px 14px', minWidth: 200, zIndex: 1000, boxShadow: '0 4px 20px rgba(0,0,0,0.5)' }}>
          <div style={{ marginBottom: 12, paddingBottom: 12, borderBottom: '1px solid #1e1e2e' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>{user.name}</div>
            <div style={{ fontSize: 10, color: '#4b5563' }}>{user.email}</div>
            <div style={{ fontSize: 9, color: '#374151', marginTop: 4 }}>가입일 {formatDate(user.created_at)}</div>
            <div style={{ marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 5, background: '#0a0a14', border: `1px solid ${planInfo.color}22`, borderRadius: 4, padding: '3px 7px' }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: planInfo.color, flexShrink: 0, display: 'inline-block' }} />
              <span style={{ fontSize: 10, color: planInfo.color, fontWeight: 600 }}>{planInfo.label} 플랜</span>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <button onClick={() => { setOpen(false); onPricingOpen(); }}
              style={{ background: 'none', border: 'none', color: '#6b7280', fontSize: 11, padding: '5px 0', textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 9, color: '#374151' }}>&#9632;</span>요금제 변경
            </button>
            <button onClick={() => { setOpen(false); onLogout(); }}
              style={{ background: 'none', border: 'none', color: '#6b7280', fontSize: 11, padding: '5px 0', textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 9, color: '#374151' }}>&#9632;</span>로그아웃
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

const ExamplePage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { models, selectedModel, setSelectedModel } = useModel();
  const [selectedStock, setSelectedStock] = useState<{ code: string; name: string } | null>(null);
  const [currentName, setCurrentName] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>('3m');
  const [sellMode, setSellMode] = useState<'ai' | 'simple'>('ai');
  const [chartInterval, setChartInterval] = useState<ChartInterval>('1d');
  const [marketUpdatedAt, setMarketUpdatedAt] = useState<string | null>(null);
  const [mobile, setMobile] = useState(isMobile());
  const [activeTab, setActiveTab] = useState<Tab>('chart');
  const [watchId, setWatchId] = useState<string | null>(null);
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [pricingModalOpen, setPricingModalOpen] = useState(false);
  const [currentPrice, setCurrentPrice] = useState<number | undefined>(undefined);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!localStorage.getItem('access_token')) { navigate('/auth'); return; }
    getMe().then(setUser).catch(() => {});
    const params = new URLSearchParams(location.search);
    const code = params.get('code');
    if (code) {
      stockApi.search(code).then((res) => {
        const found = res.data.find((s: any) => s.stock_code === code);
        if (found) { setSelectedStock({ code: found.stock_code, name: found.stock_name }); setCurrentName(found.stock_name); checkWatch(found.stock_code); }
      }).catch(() => {});
    } else {
      stockApi.getPredictions('매수', 1).then((res) => {
        if (res.data.length > 0) { const first = res.data[0]; setSelectedStock({ code: first.stock_code, name: first.stock_name }); setCurrentName(first.stock_name); }
      }).catch(() => {});
    }
  }, []);

  useEffect(() => {
    const onResize = () => setMobile(isMobile());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const checkWatch = useCallback((code: string) => {
    watchlistApi.check(code).then((res) => setWatchId(res.data.is_watching ? res.data.id : null)).catch(() => setWatchId(null));
  }, []);

  const handleSelectStock = (code: string, name: string) => {
    setSelectedStock({ code, name }); setCurrentName(name);
    if (mobile) setActiveTab('chart');
    const params = new URLSearchParams(location.search);
    params.set('code', code);
    navigate(`?${params.toString()}`, { replace: true });
    checkWatch(code);
  };

  const handleToggleWatch = async () => {
    if (!selectedStock) return;
    if (watchId) { await watchlistApi.remove(watchId); setWatchId(null); }
    else { const res = await watchlistApi.add(selectedStock.code, selectedStock.name); setWatchId(res.data.id); }
  };

  const handleLogout = () => { logout(); navigate('/auth'); };

  const TABS: { key: Tab; label: string }[] = [
    { key: 'chart', label: '차트' }, { key: 'ai', label: 'AI 예측' },
    { key: 'market', label: '글로벌' }, { key: 'winrate', label: '승률' },
  ];

  const panel = { background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: '10px 12px' };

  const intervalToggle = selectedStock ? (
    <div style={{ display: 'inline-flex', background: '#0d0d1a', border: '1px solid #2a2a3d', borderRadius: 4, overflow: 'hidden', marginLeft: 4 }}>
      {([['1d', '일봉'], ['5m', '5분']] as [ChartInterval, string][]).map(([iv, label]) => (
        <button key={iv} onClick={() => setChartInterval(iv as ChartInterval)}
          style={{ padding: '3px 10px', fontSize: 11, fontWeight: chartInterval === iv ? 600 : 400, border: 'none', borderRight: iv === '1d' ? '1px solid #2a2a3d' : 'none', cursor: 'pointer', background: chartInterval === iv ? '#1e1e35' : 'transparent', color: chartInterval === iv ? '#a5b4fc' : '#555', letterSpacing: '0.02em' }}>
          {label}
        </button>
      ))}
    </div>
  ) : null;

  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexShrink: 0, flexWrap: 'wrap' }}>
      <h1 style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', margin: 0, flexShrink: 0 }}>RichClub AI</h1>
      <StockSearchSection initialStock={selectedStock} onStockChange={handleSelectStock} searchOnly />
      {!mobile && (['1m', '3m', '6m'] as Period[]).map((p) => (
        <button key={p} onClick={() => setPeriod(p)}
          style={{ padding: '4px 10px', fontSize: 11, borderRadius: 5, border: 'none', cursor: 'pointer', background: period === p ? '#6366f1' : '#1e1e2e', color: period === p ? '#fff' : '#888' }}>{p}</button>
      ))}
      {!mobile && chartInterval === '1d' && intervalToggle}
      {!mobile && chartInterval === '5m' && (<>{intervalToggle}<span style={{ fontSize: 9, color: '#374151', letterSpacing: '0.03em' }}>LIVE · 5min</span></>)}
      {currentName && (
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ fontSize: 12, color: '#6366f1', fontWeight: 600 }}>
            — {currentName}
            {selectedStock?.code && <span style={{ fontSize: 10, color: '#4b5563', fontWeight: 400, marginLeft: 4 }}>{selectedStock.code}</span>}
          </span>
          <button onClick={handleToggleWatch} title={watchId ? '관심종목 제거' : '관심종목 추가'}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: watchId ? '#fbbf24' : '#374151', padding: '0 2px', lineHeight: 1 }}>
            {watchId ? '★' : '☆'}
          </button>
        </span>
      )}
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
        <button onClick={() => navigate('/performance')}
          style={{ fontSize: 10, padding: '3px 8px', background: '#1e1e2e', color: '#a5b4fc', border: '1px solid #3730a3', borderRadius: 4, cursor: 'pointer' }}>
          AI 실적
        </button>
        <button onClick={() => setTradeModalOpen(true)}
          style={{ fontSize: 10, padding: '3px 8px', background: '#1e1e2e', color: '#a5b4fc', border: '1px solid #3730a3', borderRadius: 4, cursor: 'pointer' }}>
          매매일지
        </button>
        <button onClick={() => window.open('/mlops', '_blank')}
          style={{ fontSize: 10, padding: '3px 8px', background: '#1e1e2e', color: '#6b7280', border: '1px solid #2d2d3d', borderRadius: 4, cursor: 'pointer' }}>
          MLOps
        </button>
        {user && <ProfileDropdown user={user} onLogout={handleLogout} onPricingOpen={() => setPricingModalOpen(true)} />}
      </div>
    </div>
  );

  const pricingModal = pricingModalOpen ? (
    <div onClick={() => setPricingModalOpen(false)}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, padding: '24px', maxWidth: 1200, width: '98vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: '#e2e8f0' }}>요금제</span>
          <button onClick={() => setPricingModalOpen(false)}
            style={{ background: 'none', border: 'none', color: '#6b7280', fontSize: 16, cursor: 'pointer', lineHeight: 1 }}>
            &#x2715;
          </button>
        </div>
        <PricingContent currentPlanId={user?.plan} onPlanChanged={(newPlan) => setUser((u) => u ? { ...u, plan: newPlan } : u)} />
      </div>
    </div>
  ) : null;

  if (mobile) {
    return (
      <div style={{ background: '#0a0a14', minHeight: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'inherit' }}>
        <div style={{ padding: '10px 12px 0', flexShrink: 0 }}>{header}</div>
        {activeTab === 'chart' && (
          <div style={{ display: 'flex', gap: 6, padding: '0 12px 8px', alignItems: 'center' }}>
            {(['1m', '3m', '6m'] as Period[]).map((p) => (
              <button key={p} onClick={() => setPeriod(p)}
                style={{ padding: '3px 10px', fontSize: 11, borderRadius: 5, border: 'none', cursor: 'pointer', background: period === p ? '#6366f1' : '#1e1e2e', color: period === p ? '#fff' : '#888' }}>{p}</button>
            ))}
            {intervalToggle}
          </div>
        )}
        <div style={{ flex: 1, padding: '0 12px', overflow: 'hidden' }}>
          {activeTab === 'chart' && (
            <div style={{ ...panel, height: 'calc(100vh - 130px)', overflow: 'hidden' }}>
              <StockSearchSection key={selectedModel} initialStock={selectedStock} onStockChange={handleSelectStock} chartOnly period={period} sellMode={sellMode} chartInterval={chartInterval} modelId={selectedModel} />
            </div>
          )}
          {activeTab === 'ai' && (
            <div style={{ ...panel, minHeight: '60vh' }}>
              <RightPanel key={selectedModel} onSelectStock={handleSelectStock} selectedCode={selectedStock?.code} onWatchChange={(code, id) => { if (code === selectedStock?.code) setWatchId(id); }} modelId={selectedModel} />
            </div>
          )}
          {activeTab === 'market' && (
            <div style={panel}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#666', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
                <span>글로벌 시장</span>
                {marketUpdatedAt && <span style={{ fontSize: 8, color: '#444', fontWeight: 400 }}>{marketUpdatedAt} KST</span>}
              </div>
              <GlobalMarketSection compact onUpdatedAt={setMarketUpdatedAt} />
            </div>
          )}
          {activeTab === 'winrate' && (
            <div style={panel}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#666', marginBottom: 8 }}>승률 테스트</div>
              <WinRateSection compact stockCode={selectedStock?.code} modelId={selectedModel} onTabChange={setSellMode} />
            </div>
          )}
        </div>
        <div style={{ display: 'flex', borderTop: '1px solid #1e1e2e', background: '#0a0a14', flexShrink: 0 }}>
          {TABS.map(({ key, label }) => (
            <button key={key} onClick={() => setActiveTab(key)}
              style={{ flex: 1, padding: '12px 0', fontSize: 11, border: 'none', cursor: 'pointer', background: activeTab === key ? '#6366f1' : 'transparent', color: activeTab === key ? '#fff' : '#555', fontWeight: activeTab === key ? 600 : 400 }}>{label}</button>
          ))}
        </div>
        {pricingModal}
      </div>
    );
  }

  return (
    <div style={{ background: '#0a0a14', height: '100vh', overflow: 'hidden', padding: '10px 14px', fontFamily: 'inherit', boxSizing: 'border-box', display: 'flex', flexDirection: 'column' }}>
      {header}
      <TradeModal isOpen={tradeModalOpen} onClose={() => setTradeModalOpen(false)} initialStockCode={selectedStock?.code} initialStockName={selectedStock?.name} initialPrice={currentPrice} />
      {pricingModal}
      <div style={{ display: 'flex', gap: 10, flex: 1, minHeight: 0 }}>
        <div style={{ width: 190, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto' }}>
          {models.length > 0 && (
            <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: '8px 12px' }}>
              <div style={{ fontSize: 9, color: '#4b5563', marginBottom: 6 }}>AI 모델</div>
              <select
                value={selectedModel}
                onChange={(e) => {
                  const model = models.find((m) => m.id === e.target.value);
                  if (model?.available) setSelectedModel(e.target.value);
                }}
                style={{ width: '100%', background: '#1e1e2e', border: '1px solid #2d2d3d', borderRadius: 4, color: '#a5b4fc', fontSize: 11, fontWeight: 600, padding: '4px 8px', cursor: 'pointer', outline: 'none' }}
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id} disabled={!m.available}
                    style={{ color: m.available ? '#a5b4fc' : '#4b5563' }}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div style={panel}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#666', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>글로벌 시장</span>
              {marketUpdatedAt && <span style={{ fontSize: 8, color: '#444', fontWeight: 400 }}>{marketUpdatedAt} KST</span>}
            </div>
            <GlobalMarketSection compact onUpdatedAt={setMarketUpdatedAt} />
          </div>
          <div style={panel}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#666' }}>승률 테스트</span>
              {currentName && (
                <span style={{ fontSize: 9, color: '#6366f1' }}>
                  — {currentName}
                  {selectedStock?.code && <span style={{ color: '#4b5563', marginLeft: 3 }}>{selectedStock.code}</span>}
                </span>
              )}
            </div>
            <WinRateSection compact stockCode={selectedStock?.code} modelId={selectedModel} onTabChange={setSellMode} />
          </div>
        </div>
        <div style={{ flex: 1, minWidth: 0, ...panel, overflow: 'hidden' }}>
          <StockSearchSection key={selectedModel} initialStock={selectedStock} onStockChange={handleSelectStock} chartOnly period={period} sellMode={sellMode} chartInterval={chartInterval} onPriceUpdate={setCurrentPrice} modelId={selectedModel} />
        </div>
        <div style={{ width: 195, flexShrink: 0, ...panel, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 0 }}>
          <RightPanel key={selectedModel} onSelectStock={handleSelectStock} selectedCode={selectedStock?.code} onWatchChange={(code, id) => { if (code === selectedStock?.code) setWatchId(id); }} modelId={selectedModel} />
        </div>
      </div>
    </div>
  );
};

export default ExamplePage;
