import React from 'react';
import GlobalMarketSection from '../containers/example/GlobalMarketSection';
import AIPredictionsSection from '../containers/example/AIPredictionsSection';
import StockSearchSection from '../containers/example/StockSearchSection';
import WinRateSection from '../containers/example/WinRateSection';
import '../styles/example.css';

const ExamplePage: React.FC = () => {
  return (
    <div className="ex-wrap">
      <h1 className="ex-title">RichClub API 데모</h1>

      <section className="ex-section">
        <h2 className="ex-section-title">글로벌 시장 현황</h2>
        <GlobalMarketSection />
      </section>

      <section className="ex-section">
        <h2 className="ex-section-title">AI 예측 목록</h2>
        <AIPredictionsSection />
      </section>

      <section className="ex-section">
        <h2 className="ex-section-title">종목 차트 (RSI / MACD / 5분봉)</h2>
        <StockSearchSection />
      </section>

      <section className="ex-section">
        <h2 className="ex-section-title">승률 테스트</h2>
        <WinRateSection />
      </section>
    </div>
  );
};

export default ExamplePage;
