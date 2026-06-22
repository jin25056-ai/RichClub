import React, { useEffect, useState } from 'react';
import { marketApi, GlobalMarketResponse } from '../../api/stock';

const SIGNAL_COLOR: Record<string, string> = {
  '매수 우호': '#16a34a', '매수 비우호': '#dc2626', '중립': '#d97706',
};

interface Props {
  compact?: boolean;
}

const GlobalMarketSection: React.FC<Props> = ({ compact }) => {
  const [data, setData] = useState<GlobalMarketResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () => {
      marketApi.getGlobal()
        .then((res) => setData(res.data))
        .finally(() => setLoading(false));
    };
    load();
    // 서버 캐시가 10분이므로 10분마다 자동 갱신
    const timer = setInterval(load, 10 * 60 * 1000);
    return () => clearInterval(timer);
  }, []);

  if (loading) return <div style={{ fontSize: 11, color: '#666' }}>불러오는 중...</div>;
  if (!data) return null;

  const signalColor = SIGNAL_COLOR[data.invest_signal] ?? '#d97706';
  const updatedAt = new Date(data.updated_at).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });

  if (compact) {
    return (
      <div>
        {/* 투자 신호 */}
        <div style={{
          padding: '6px 10px', borderRadius: 6, marginBottom: 8,
          background: signalColor + '22', border: `1px solid ${signalColor}55`,
        }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: signalColor }}>{data.invest_signal}</div>
          <div style={{ fontSize: 10, color: '#888', marginTop: 2 }}>{data.invest_reason}</div>
        </div>

        {/* 지수 목록 */}
        {data.items.map((item) => (
          <div key={item.symbol} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '4px 0', borderBottom: '1px solid #13131e',
          }}>
            <span style={{ fontSize: 10, color: '#888' }}>{item.name}</span>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 11, color: '#d1d5db' }}>
                {item.price != null ? item.price.toLocaleString() : '-'}
              </div>
              <div style={{
                fontSize: 10,
                color: item.change_pct == null ? '#555' : item.change_pct >= 0 ? '#16a34a' : '#dc2626',
              }}>
                {item.change_pct != null ? `${item.change_pct >= 0 ? '+' : ''}${item.change_pct.toFixed(2)}%` : '-'}
              </div>
            </div>
          </div>
        ))}

        {/* 업데이트 시간 */}
        <div style={{ marginTop: 6, fontSize: 9, color: '#444', textAlign: 'right', whiteSpace: 'nowrap' }}>
          {updatedAt} KST 기준
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="ex-signal-box" style={{ borderColor: signalColor }}>
        <span className="ex-signal-label" style={{ color: signalColor }}>{data.invest_signal}</span>
        <span className="ex-signal-reason">{data.invest_reason}</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#666' }}>기준: {updatedAt} KST</span>
      </div>
      <div className="ex-market-grid">
        {data.items.map((item) => (
          <div key={item.symbol} className="ex-market-card">
            <div className="ex-market-name">{item.name}</div>
            <div className="ex-market-price">{item.price != null ? item.price.toLocaleString() : '-'}</div>
            <div className="ex-market-change" style={{ color: item.change_pct == null ? '#888' : item.change_pct >= 0 ? '#16a34a' : '#dc2626' }}>
              {item.change_pct != null ? `${item.change_pct >= 0 ? '+' : ''}${item.change_pct.toFixed(2)}%` : '-'}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default GlobalMarketSection;
