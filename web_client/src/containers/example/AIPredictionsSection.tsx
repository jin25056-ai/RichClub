import React, { useEffect, useState } from 'react';
import { stockApi, AIPredictionItem } from '../../api/stock';

type SignalFilter = '' | '매수' | '매도' | '관망';

const SIGNAL_COLOR: Record<string, string> = {
  매수: '#16a34a', 매도: '#dc2626', 관망: '#d97706',
};

const AIPredictionsSection: React.FC = () => {
  const [items, setItems] = useState<AIPredictionItem[]>([]);
  const [filter, setFilter] = useState<SignalFilter>('매수');
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchPredictions = (signal: SignalFilter) => {
    setLoading(true);
    stockApi.getPredictions(signal || undefined, 30)
      .then((res) => setItems(res.data))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchPredictions(filter); }, [filter]);

  const handleDetail = (stock_code: string) => {
    setDetailLoading(true);
    stockApi.getAIDetail(stock_code)
      .then((res) => setDetail(res.data))
      .finally(() => setDetailLoading(false));
  };

  return (
    <div>
      <div className="ex-filter-row">
        {(['', '매수', '매도', '관망'] as SignalFilter[]).map((s) => (
          <button
            key={s}
            className={`ex-filter-btn${filter === s ? ' active' : ''}`}
            onClick={() => setFilter(s)}
          >
            {s || '전체'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="ex-loading">불러오는 중...</div>
      ) : (
        <div className="ex-table-wrap">
          <table className="ex-table">
            <thead>
              <tr>
                <th>종목코드</th><th>종목명</th><th>신호</th>
                <th>현재가</th><th>신뢰도</th><th>상세</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.stock_code + item.predicted_at}>
                  <td>{item.stock_code}</td>
                  <td>{item.stock_name}</td>
                  <td>
                    <span className="ex-badge" style={{ background: SIGNAL_COLOR[item.signal] }}>
                      {item.signal}
                    </span>
                  </td>
                  <td>{item.current_price != null ? item.current_price.toLocaleString() : '-'}</td>
                  <td>{item.confidence != null ? `${(item.confidence * 100).toFixed(1)}%` : '-'}</td>
                  <td>
                    <button className="ex-btn-sm" onClick={() => handleDetail(item.stock_code)}>
                      보기
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detail && (
        <div className="ex-detail-panel">
          <div className="ex-detail-header">
            <span>{detail.stock_name} ({detail.stock_code})</span>
            <span className="ex-badge" style={{ background: SIGNAL_COLOR[detail.signal] }}>
              {detail.signal}
            </span>
            {detail.confidence != null && (
              <span className="ex-confidence">신뢰도 {(detail.confidence * 100).toFixed(1)}%</span>
            )}
            <button className="ex-btn-sm" onClick={() => setDetail(null)}>닫기</button>
          </div>

          <div className="ex-detail-body">
            <div className="ex-detail-col">
              <h4>충족 조건</h4>
              {detail.conditions_met.length > 0
                ? detail.conditions_met.map((c: string) => (
                    <div key={c} className="ex-cond met">✓ {c}</div>
                  ))
                : <div style={{ fontSize: 12, color: '#555' }}>없음</div>
              }
            </div>
            <div className="ex-detail-col">
              <h4>미충족 조건</h4>
              {detail.conditions_not_met.length > 0
                ? detail.conditions_not_met.map((c: string) => (
                    <div key={c} className="ex-cond not">✗ {c}</div>
                  ))
                : <div style={{ fontSize: 12, color: '#555' }}>없음</div>
              }
            </div>
            <div className="ex-detail-col">
              <h4>기술 지표 현황</h4>
              {detailLoading ? <div className="ex-loading">로딩중...</div> :
                detail.feature_importance.length > 0
                  ? detail.feature_importance.slice(0, 8).map((f: any) => {
                      // importance가 있으면 중요도, 없으면 실제 지표값 표시
                      const hasImportance = f.importance != null && !isNaN(f.importance);
                      const displayVal = hasImportance
                        ? `${(f.importance * 100).toFixed(1)}%`
                        : f.value != null ? String(f.value) : '-';
                      const barPct = hasImportance ? f.importance * 100 : 0;
                      return (
                        <div key={f.feature} className="ex-fi-row">
                          <span className="ex-fi-name">{f.feature}</span>
                          {hasImportance && (
                            <div className="ex-fi-bar-wrap">
                              <div className="ex-fi-bar" style={{ width: `${barPct.toFixed(0)}%` }} />
                            </div>
                          )}
                          <span className="ex-fi-val" style={{ width: hasImportance ? 36 : 'auto' }}>
                            {displayVal}
                          </span>
                        </div>
                      );
                    })
                  : <div style={{ fontSize: 12, color: '#555' }}>데이터 없음</div>
              }
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AIPredictionsSection;
