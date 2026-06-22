import React, { useEffect, useState } from 'react';
import { marketApi, GlobalMarketResponse } from '../../api/stock';

const GlobalMarketSection: React.FC = () => {
  const [data, setData] = useState<GlobalMarketResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    marketApi.getGlobal()
      .then((res) => setData(res.data))
      .catch(() => setError('글로벌 시장 데이터를 불러오지 못했습니다.'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="ex-loading">불러오는 중...</div>;
  if (error) return <div className="ex-error">{error}</div>;
  if (!data) return null;

  const signalColor = data.invest_signal === '매수 우호' ? '#16a34a'
    : data.invest_signal === '매수 비우호' ? '#dc2626' : '#d97706';

  // 업데이트 시간 (KST 변환)
  const updatedAt = new Date(data.updated_at);
  const kstStr = updatedAt.toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });

  return (
    <div>
      <div className="ex-signal-box" style={{ borderColor: signalColor }}>
        <span className="ex-signal-label" style={{ color: signalColor }}>
          {data.invest_signal}
        </span>
        <span className="ex-signal-reason">{data.invest_reason}</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#666' }}>
          기준: {kstStr} KST
        </span>
      </div>

      <div className="ex-market-grid">
        {data.items.map((item) => (
          <div key={item.symbol} className="ex-market-card">
            <div className="ex-market-name">{item.name}</div>
            <div className="ex-market-price">
              {item.price != null ? item.price.toLocaleString() : '-'}
            </div>
            <div
              className="ex-market-change"
              style={{ color: item.change_pct == null ? '#888' : item.change_pct >= 0 ? '#16a34a' : '#dc2626' }}
            >
              {item.change_pct != null
                ? `${item.change_pct >= 0 ? '+' : ''}${item.change_pct.toFixed(2)}%`
                : '-'}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default GlobalMarketSection;
