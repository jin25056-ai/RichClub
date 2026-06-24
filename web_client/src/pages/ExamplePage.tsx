import React, { useState, useEffect } from 'react';
import GlobalMarketSection from '../containers/example/GlobalMarketSection';
import AIPredictionsSection from '../containers/example/AIPredictionsSection';
import StockSearchSection from '../containers/example/StockSearchSection';
import WinRateSection from '../containers/example/WinRateSection';
import { stockApi } from '../api/stock';
import '../styles/example.css';

type Period = '1m' | '3m' | '6m';

const ExamplePage: React.FC = () => {
  const [selectedStock, setSelectedStock] = useState<{ code: string; name: string } | null>(null);
  const [currentName, setCurrentName] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>('3m');

  useEffect(() => {
    stockApi.getPredictions('매수', 1).then((res) => {
      if (res.data.length > 0) {
        const first = res.data[0];
        setSelectedStock({ code: first.stock_code, name: first.stock_name });
        setCurrentName(first.stock_name);
      }
    }).catch(() => {});
  }, []);

  const handleSelectStock = (code: string, name: string) => {
    setSelectedStock({ code, name });
    setCurrentName(name);
  };

  return (
    <div style={{ background: '#0a0a14', height: '100vh', overflow: 'hidden', padding: '10px 14px', fontFamily: 'inherit', boxSizing: 'border-box', display: 'flex', flexDirection: 'column' }}>

      {/* 상단 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexShrink: 0, height: 36 }}>
        <h1 style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', margin: 0, flexShrink: 0 }}>RichClub AI</h1>
        <StockSearchSection initialStock={selectedStock} onStockChange={handleSelectStock} searchOnly />
        {(['1m', '3m', '6m'] as Period[]).map((p) => (
          <button key={p} onClick={() => setPeriod(p)}
            style={{
              padding: '4px 10px', fontSize: 11, borderRadius: 5, border: 'none', cursor: 'pointer',
              background: period === p ? '#6366f1' : '#1e1e2e',
              color: period === p ? '#fff' : '#888',
            }}>{p}</button>
        ))}
        {currentName && (
          <span style={{ fontSize: 12, color: '#6366f1', fontWeight: 600, marginLeft: 4 }}>
            — {currentName}
          </span>
        )}
      </div>

      {/* 메인 레이아웃 */}
      <div style={{ display: 'flex', gap: 10, flex: 1, minHeight: 0 }}>

        {/* 좌측 */}
        <div style={{ width: 190, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto' }}>
          <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#666', marginBottom: 8 }}>글로벌 시장</div>
            <GlobalMarketSection compact />
          </div>
          <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#666' }}>승률 테스트</span>
              {currentName && (
                <span style={{ fontSize: 9, color: '#6366f1' }}>— {currentName}</span>
              )}
            </div>
            <WinRateSection compact stockCode={selectedStock?.code} />
          </div>
        </div>

        {/* 가운데: 차트 */}
        <div style={{ flex: 1, minWidth: 0, background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: '8px 12px', overflow: 'hidden' }}>
          <StockSearchSection initialStock={selectedStock} onStockChange={handleSelectStock} chartOnly period={period} />
        </div>

        {/* 우측: AI 예측 목록 */}
        <div style={{ width: 195, flexShrink: 0, background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
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
