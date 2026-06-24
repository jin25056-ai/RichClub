import React, { useState } from 'react';
import { stockApi, AIPredictionItem } from '../../api/stock';

type SignalFilter = '' | '매수' | '매도' | '관망';

const SIGNAL_COLOR: Record<string, string> = {
  매수: '#16a34a', 매도: '#dc2626', 관망: '#d97706',
};
const SIGNAL_BG: Record<string, string> = {
  매수: '#14532d', 매도: '#7f1d1d', 관망: '#78350f',
};

interface Props {
  onSelectStock: (stockCode: string, stockName: string) => void;
  selectedCode?: string;
}

const fmtPrice = (p: number) =>
  p >= 1000000 ? `${(p / 1000000).toFixed(1)}M`
  : p >= 1000  ? `${Math.round(p / 1000)}K`
  : String(p);

const fmtDate = (s: string) => {
  if (!s) return '';
  const d = new Date(s);
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${m}.${day}`;
};

const AIPredictionsSection: React.FC<Props> = ({ onSelectStock, selectedCode }) => {
  const [items, setItems] = useState<AIPredictionItem[]>([]);
  const [filter, setFilter] = useState<SignalFilter>('');
  const [loading, setLoading] = useState(false);

  const fetchPredictions = (signal: SignalFilter) => {
    setLoading(true);
    stockApi.getPredictions(signal || undefined, 100)
      .then((res) => setItems(res.data))
      .finally(() => setLoading(false));
  };

  React.useEffect(() => { fetchPredictions(''); }, []);

  const handleFilter = (s: SignalFilter) => {
    setFilter(s);
    fetchPredictions(s);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 필터 */}
      <div style={{ display: 'flex', gap: 4, padding: '6px 8px', borderBottom: '1px solid #1e1e2e', flexWrap: 'wrap' }}>
        {(['', '매수', '매도', '관망'] as SignalFilter[]).map((s) => (
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

      {/* 목록 */}
      {loading ? (
        <div style={{ padding: 10, fontSize: 11, color: '#666' }}>불러오는 중...</div>
      ) : (
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {items.map((item) => {
            const isActive = selectedCode === item.stock_code;
            return (
              <div key={item.stock_code}
                onClick={() => onSelectStock(item.stock_code, item.stock_name)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '5px 10px', cursor: 'pointer', borderBottom: '1px solid #13131e',
                  background: isActive ? '#1a1a30' : 'transparent',
                }}
                onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = '#151525'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = isActive ? '#1a1a30' : 'transparent'; }}
              >
                {/* 신호 뱃지 */}
                <span style={{
                  width: 26, textAlign: 'center', fontSize: 9, padding: '1px 2px', borderRadius: 3, flexShrink: 0,
                  background: SIGNAL_BG[item.signal], color: SIGNAL_COLOR[item.signal], fontWeight: 700,
                }}>
                  {item.signal}
                </span>

                {/* 종목명 + 코드 + 날짜 */}
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

                {/* 현재가 + 변화율 */}
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: 10, color: '#9ca3af' }}>
                    {item.current_price != null ? fmtPrice(item.current_price) : '-'}
                  </div>
                  {item.change_pct != null && (
                    <div style={{
                      fontSize: 9,
                      color: item.change_pct > 0 ? '#16a34a' : item.change_pct < 0 ? '#dc2626' : '#6b7280',
                    }}>
                      {item.change_pct > 0 ? '+' : ''}{item.change_pct.toFixed(2)}%
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default AIPredictionsSection;
