import React, { useEffect, useState, useRef } from 'react';
import { marketApi, GlobalMarketResponse } from '../../api/stock';

const SIGNAL_COLOR: Record<string, string> = {
  '매수 우호': '#16a34a', '매수 비우호': '#dc2626', '중립': '#d97706',
};

interface Props {
  compact?: boolean;
}

const SCORE_RULES: Record<string, { label: string; conditions: { desc: string; score: number; check?: (pct: number) => boolean; checkPrice?: (p: number) => boolean }[] }> = {
  '^IXIC':    { label: '나스닥',          conditions: [{ desc: '+1% 이상', score: +2, check: (p) => p >= 1.0 }, { desc: '-1% 이하', score: -2, check: (p) => p <= -1.0 }] },
  '^GSPC':    { label: 'S&P500',          conditions: [{ desc: '+1% 이상', score: +1, check: (p) => p >= 1.0 }, { desc: '-1% 이하', score: -1, check: (p) => p <= -1.0 }] },
  '^SOX':     { label: '필라델피아 반도체', conditions: [{ desc: '+2% 이상', score: +1, check: (p) => p >= 2.0 }, { desc: '-2% 이하', score: -1, check: (p) => p <= -2.0 }] },
  '^VIX':     { label: 'VIX',             conditions: [{ desc: '15 미만', score: +1, checkPrice: (p) => p < 15 }, { desc: '25 초과', score: -2, checkPrice: (p) => p > 25 }] },
  'USDKRW=X': { label: '달러/원',          conditions: [{ desc: '-0.5% 이하 (원화강세)', score: +1, check: (p) => p <= -0.5 }, { desc: '+1% 이상 (원화약세)', score: -1, check: (p) => p >= 1.0 }] },
  'CL=F':     { label: 'WTI 원유',        conditions: [{ desc: '+3% 이상 급등', score: -1, check: (p) => p >= 3.0 }] },
  'GC=F':     { label: '금',              conditions: [{ desc: '+1% 이상 (위험회피)', score: -1, check: (p) => p >= 1.0 }] },
};

const GlobalMarketSection: React.FC<Props> = ({ compact }) => {
  const [data, setData] = useState<GlobalMarketResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [showInfo, setShowInfo] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const [popupPos, setPopupPos] = useState<{ top: number; left: number } | null>(null);

  const handleInfoClick = () => {
    if (!showInfo && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      setPopupPos({ top: rect.top, left: rect.right + 8 });
    }
    setShowInfo((v) => !v);
  };

  useEffect(() => {
    const load = () => {
      marketApi.getGlobal()
        .then((res) => setData(res.data))
        .finally(() => setLoading(false));
    };
    load();
    const timer = setInterval(load, 10 * 60 * 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!showInfo) return;
    const handleClick = (e: MouseEvent) => {
      if (btnRef.current && !btnRef.current.contains(e.target as Node)) {
        setShowInfo(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showInfo]);

  if (loading) return <div style={{ fontSize: 11, color: '#666' }}>불러오는 중...</div>;
  if (!data) return null;

  const signalColor = SIGNAL_COLOR[data.invest_signal] ?? '#d97706';
  const updatedAt = new Date(data.updated_at).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });

  // 점수 상세 계산
  const itemMap: Record<string, any> = {};
  (data.items || []).forEach((it: any) => { itemMap[it.symbol] = it; });

  const scoreRows = Object.entries(SCORE_RULES).map(([symbol, rule]) => {
    const item = itemMap[symbol];
    if (!item) return null;
    const value = item.change_pct != null
      ? `${item.change_pct >= 0 ? '+' : ''}${item.change_pct.toFixed(2)}%`
      : item.price?.toLocaleString() ?? '-';
    const triggered = rule.conditions.find((c) =>
      c.checkPrice ? item.price != null && c.checkPrice(item.price)
                   : item.change_pct != null && c.check!(item.change_pct)
    );
    return {
      label: rule.label,
      value,
      triggeredDesc: triggered?.desc ?? null,
      score: triggered?.score ?? 0,
      triggered: !!triggered,
    };
  }).filter(Boolean) as { label: string; value: string; triggeredDesc: string | null; score: number; triggered: boolean }[];

  const totalScore = scoreRows.filter((r) => r.triggered).reduce((s, r) => s + r.score, 0);

  if (compact) {
    return (
      <div>
        {/* 투자 신호 */}
        <div style={{
          padding: '6px 10px', borderRadius: 6, marginBottom: 8,
          background: signalColor + '22', border: `1px solid ${signalColor}55`,
          position: 'relative', overflow: 'visible',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: signalColor }}>{data.invest_signal}</div>
            {/* i 버튼 */}
            <div style={{ position: 'relative' }}>
              <button
                ref={btnRef}
                onClick={handleInfoClick}
                style={{
                  width: 16, height: 16, borderRadius: '50%', border: '1px solid #555',
                  background: '#1e1e2e', color: '#888',
                  fontSize: 9, fontWeight: 700, cursor: 'pointer', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', lineHeight: 1,
                }}>i</button>

              {/* 상세 팝업 - 우측으로 */}
              {showInfo && popupPos && (
                <div style={{
                  position: 'fixed', top: popupPos.top, left: popupPos.left, zIndex: 9999,
                  background: '#12121f', border: '1px solid #2d2d3d', borderRadius: 8,
                  padding: '10px 12px', width: 230, boxShadow: '0 4px 20px rgba(0,0,0,0.8)',
                }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: '#aaa', marginBottom: 8 }}>
                    점수 기준 상세
                  </div>
                  {scoreRows.map((r, i) => (
                    <div key={i} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '4px 0', borderBottom: '1px solid #1e1e2e',
                    }}>
                      <div>
                        <span style={{ fontSize: 9, color: r.triggered ? '#e2e8f0' : '#888' }}>{r.label}</span>
                        {r.triggeredDesc && (
                          <span style={{ fontSize: 8, color: r.score > 0 ? '#16a34a' : '#dc2626', marginLeft: 4 }}>
                            {r.triggeredDesc}
                          </span>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{
                          fontSize: 9,
                          color: r.triggered ? (r.score > 0 ? '#16a34a' : '#dc2626') : '#6b7280',
                        }}>{r.value}</span>
                        <span style={{
                          fontSize: 9, fontWeight: 700, minWidth: 24, textAlign: 'right',
                          color: r.triggered ? (r.score > 0 ? '#16a34a' : '#dc2626') : '#444',
                        }}>
                          {r.triggered ? (r.score > 0 ? `+${r.score}` : `${r.score}`) : '-'}
                        </span>
                      </div>
                    </div>
                  ))}
                  <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginTop: 8, paddingTop: 6, borderTop: '1px solid #2d2d3d',
                  }}>
                    <span style={{ fontSize: 9, color: '#888' }}>합계 점수</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: totalScore >= 2 ? '#16a34a' : totalScore <= -2 ? '#dc2626' : '#d97706' }}>
                      {totalScore > 0 ? `+${totalScore}` : totalScore}
                    </span>
                  </div>
                  <div style={{ marginTop: 6, fontSize: 8, color: '#444', lineHeight: 1.4 }}>
                    +2 이상 매수 우호 / -2 이하 매수 비우호 / 그 외 중립
                  </div>
                </div>
              )}
            </div>
          </div>
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
