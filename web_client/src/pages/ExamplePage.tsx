import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import GlobalMarketSection from '../containers/example/GlobalMarketSection';
import AIPredictionsSection from '../containers/example/AIPredictionsSection';
import StockSearchSection from '../containers/example/StockSearchSection';
import WinRateSection from '../containers/example/WinRateSection';
import { stockApi } from '../api/stock';
import '../styles/example.css';

type Period = '1m' | '3m' | '6m';
type Tab = 'chart' | 'ai' | 'market' | 'winrate';

const isMobile = () => window.innerWidth <= 768;

const ExamplePage: React.FC = () => {
  const navigate = useNavigate();
  const [selectedStock, setSelectedStock] = useState<{ code: string; name: string } | null>(null);
  const [currentName, setCurrentName] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>('3m');
  const [sellMode, setSellMode] = useState<'ai' | 'simple'>('ai');
  const [marketUpdatedAt, setMarketUpdatedAt] = useState<string | null>(null);
  const [mobile, setMobile] = useState(isMobile());
  const [activeTab, setActiveTab] = useState<Tab>('chart');

  useEffect(() => {
    if (!localStorage.getItem('access_token')) {
      navigate('/auth');
      return;
    }
    stockApi.getPredictions('매수', 1).then((res) => {
      if (res.data.length > 0) {
        const first = res.data[0];
        setSelectedStock({ code: first.stock_code, name: first.stock_name });
        setCurrentName(first.stock_name);
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const onResize = () => setMobile(isMobile());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const handleSelectStock = (code: string, name: string) => {
    setSelectedStock({ code, name });
    setCurrentName(name);
    if (mobile) setActiveTab('chart');
  };

  const TABS: { key: Tab; label: string }[] = [
    { key: 'chart',   label: '차트' },
    { key: 'ai',      label: 'AI 예측' },
    { key: 'market',  label: '글로벌' },
    { key: 'winrate', label: '승률' },
  ];

  // 공통 패널 스타일
  const panel = { background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: '10px 12px' };

  // 상단 헤더
  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexShrink: 0, flexWrap: 'wrap' }}>
      <h1 style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', margin: 0, flexShrink: 0 }}>RichClub AI</h1>
      <StockSearchSection initialStock={selectedStock} onStockChange={handleSelectStock} searchOnly />
      {!mobile && (['1m', '3m', '6m'] as Period[]).map((p) => (
        <button key={p} onClick={() => setPeriod(p)}
          style={{ padding: '4px 10px', fontSize: 11, borderRadius: 5, border: 'none', cursor: 'pointer', background: period === p ? '#6366f1' : '#1e1e2e', color: period === p ? '#fff' : '#888' }}>{p}</button>
      ))}
      {currentName && (
        <span style={{ fontSize: 12, color: '#6366f1', fontWeight: 600 }}>
          — {currentName}
          {selectedStock?.code && <span style={{ fontSize: 10, color: '#4b5563', fontWeight: 400, marginLeft: 4 }}>{selectedStock.code}</span>}
        </span>
      )}
      <div style={{ marginLeft: 'auto' }}>
        <button onClick={() => window.open('/mlops', '_blank')}
          style={{ fontSize: 10, padding: '3px 8px', background: '#1e1e2e', color: '#6b7280', border: '1px solid #2d2d3d', borderRadius: 4, cursor: 'pointer' }}>
          MLOps
        </button>
      </div>
    </div>
  );

  if (mobile) {
    return (
      <div style={{ background: '#0a0a14', minHeight: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'inherit' }}>
        {/* 헤더 */}
        <div style={{ padding: '10px 12px 0', flexShrink: 0 }}>{header}</div>

        {/* 기간 선택 (모바일) */}
        {activeTab === 'chart' && (
          <div style={{ display: 'flex', gap: 6, padding: '0 12px 8px' }}>
            {(['1m', '3m', '6m'] as Period[]).map((p) => (
              <button key={p} onClick={() => setPeriod(p)}
                style={{ padding: '3px 10px', fontSize: 11, borderRadius: 5, border: 'none', cursor: 'pointer', background: period === p ? '#6366f1' : '#1e1e2e', color: period === p ? '#fff' : '#888' }}>{p}</button>
            ))}
          </div>
        )}

        {/* 탭 콘텐츠 */}
        <div style={{ flex: 1, padding: '0 12px', overflow: 'hidden' }}>
          {activeTab === 'chart' && (
            <div style={{ ...panel, height: 'calc(100vh - 130px)', overflow: 'hidden' }}>
              <StockSearchSection initialStock={selectedStock} onStockChange={handleSelectStock} chartOnly period={period} sellMode={sellMode} />
            </div>
          )}
          {activeTab === 'ai' && (
            <div style={{ ...panel, minHeight: '60vh' }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#666', marginBottom: 8 }}>AI 예측 목록</div>
              <AIPredictionsSection onSelectStock={handleSelectStock} selectedCode={selectedStock?.code} />
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
              <WinRateSection compact stockCode={selectedStock?.code} onTabChange={setSellMode} />
            </div>
          )}
        </div>

        {/* 하단 탭 바 */}
        <div style={{ display: 'flex', borderTop: '1px solid #1e1e2e', background: '#0a0a14', flexShrink: 0 }}>
          {TABS.map(({ key, label }) => (
            <button key={key} onClick={() => setActiveTab(key)}
              style={{
                flex: 1, padding: '12px 0', fontSize: 11, border: 'none', cursor: 'pointer',
                background: activeTab === key ? '#6366f1' : 'transparent',
                color: activeTab === key ? '#fff' : '#555',
                fontWeight: activeTab === key ? 600 : 400,
              }}>{label}</button>
          ))}
        </div>
      </div>
    );
  }

  // 데스크탑 레이아웃
  return (
    <div style={{ background: '#0a0a14', height: '100vh', overflow: 'hidden', padding: '10px 14px', fontFamily: 'inherit', boxSizing: 'border-box', display: 'flex', flexDirection: 'column' }}>
      {header}
      <div style={{ display: 'flex', gap: 10, flex: 1, minHeight: 0 }}>
        <div style={{ width: 190, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto' }}>
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
            <WinRateSection compact stockCode={selectedStock?.code} onTabChange={setSellMode} />
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0, ...panel, overflow: 'hidden' }}>
          <StockSearchSection initialStock={selectedStock} onStockChange={handleSelectStock} chartOnly period={period} sellMode={sellMode} />
        </div>

        <div style={{ width: 195, flexShrink: 0, ...panel, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 0 }}>
          <div style={{ padding: '8px 10px', borderBottom: '1px solid #1e1e2e', fontSize: 11, fontWeight: 600, color: '#666', flexShrink: 0 }}>
            AI 예측 목록
          </div>
          <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <AIPredictionsSection onSelectStock={handleSelectStock} selectedCode={selectedStock?.code} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ExamplePage;
