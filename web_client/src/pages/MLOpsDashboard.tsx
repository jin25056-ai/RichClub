import React, { useState, useEffect, useCallback } from 'react';
import apiClient from '../api/client';

interface ModelStatus {
  model_exists: boolean;
  last_trained_at: string | null;
  last_accuracy: number | null;
  total_signals: number;
  returns_calculated: number;
  pending_returns: number;
}

interface MonthlyPerf {
  month: string;
  signal: string;
  total: number;
  correct: number;
  accuracy: number;
  avg_ret_5d: number;
  avg_ret_1d: number;
}

interface SignalStat {
  signal: string;
  total: number;
  correct: number;
  accuracy: number;
  avg_ret_1d: number;
  avg_ret_5d: number;
  avg_ret_20d: number;
}

interface RecentSignal {
  stock_name: string;
  stock_code: string;
  signal: string;
  predicted_at: string;
  close: number | null;
  ret_1d: number | null;
  ret_5d: number | null;
  ret_20d: number | null;
  is_correct_5d: boolean | null;
}

interface TrainHistory {
  trained_at: string;
  triggered_by: string;
  accuracy: number;
  n_train: number;
  elapsed_sec: number;
  stocks_used: number;
}

const SIG_COLOR: Record<string, string> = { '매수': '#16a34a', '매도': '#dc2626', '관망': '#d97706' };
const SIG_BG: Record<string, string> = { '매수': '#14532d', '매도': '#7f1d1d', '관망': '#78350f' };

const fmtDate = (s: string | null) => {
  if (!s) return '-';
  const d = new Date(s);
  return `${d.getMonth() + 1}.${String(d.getDate()).padStart(2, '0')}`;
};

const fmtRet = (v: number | null) => {
  if (v == null) return <span style={{ color: '#4b5563' }}>-</span>;
  return <span style={{ color: v >= 0 ? '#16a34a' : '#dc2626' }}>{v >= 0 ? '+' : ''}{v.toFixed(1)}%</span>;
};

const card = (children: React.ReactNode, style?: React.CSSProperties) => (
  <div style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: '12px 14px', ...style }}>
    {children}
  </div>
);

const MLOpsDashboard: React.FC = () => {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [monthly, setMonthly] = useState<MonthlyPerf[]>([]);
  const [stats, setStats] = useState<SignalStat[]>([]);
  const [recent, setRecent] = useState<RecentSignal[]>([]);
  const [history, setHistory] = useState<TrainHistory[]>([]);
  const [statsDays, setStatsDays] = useState(90);
  const [recentDays, setRecentDays] = useState(7);
  const [signalFilter, setSignalFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const [trainLoading, setTrainLoading] = useState(false);

  const isLoggedIn = !!localStorage.getItem('access_token');

  useEffect(() => {
    if (!isLoggedIn) {
      window.location.href = '/auth';
    }
  }, [isLoggedIn]);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/auth';
  };

  const load = useCallback(async () => {
    if (!isLoggedIn) return;
    setLoading(true);
    try {
      const [s, m, st, r, h] = await Promise.all([
        apiClient.get<ModelStatus>('/api/v1/mlops/status'),
        apiClient.get<MonthlyPerf[]>('/api/v1/mlops/monthly-performance'),
        apiClient.get<SignalStat[]>(`/api/v1/mlops/signal-stats?days=${statsDays}`),
        apiClient.get<RecentSignal[]>(`/api/v1/mlops/recent-signals?days=${recentDays}${signalFilter ? `&signal=${signalFilter}` : ''}`),
        apiClient.get<TrainHistory[]>('/api/v1/mlops/train-history'),
      ]);
      setStatus(s.data);
      setMonthly(m.data);
      setStats(st.data);
      setRecent(r.data);
      setHistory(h.data);
    } catch (e: any) {
      if (e?.response?.status === 401) {
        window.location.href = '/auth';
        return;
      }
      setMsg('데이터 로드 실패');
    }
    setLoading(false);
  }, [statsDays, recentDays, signalFilter, isLoggedIn]);

  useEffect(() => { load(); }, [load]);



  const handleTrain = async () => {
    setTrainLoading(true);
    setMsg('학습 중... (수분 소요)');
    try {
      const res = await apiClient.post('/api/v1/mlops/train');
      setMsg(`학습 완료: 정확도 ${(res.data.accuracy * 100).toFixed(1)}%`);
      load();
    } catch { setMsg('학습 실패'); }
    setTrainLoading(false);
  };

  // 월별 데이터를 월 단위로 묶어서 매수/매도/관망 함께 표시
  const monthlyGrouped = monthly.reduce((acc, m) => {
    if (!acc[m.month]) acc[m.month] = {};
    acc[m.month][m.signal] = m;
    return acc;
  }, {} as Record<string, Record<string, MonthlyPerf>>);
  const monthKeys = Object.keys(monthlyGrouped).sort().reverse().slice(0, 12);

  return (
    <div style={{ background: '#0a0a14', minHeight: '100vh', padding: '14px 18px', color: '#e2e8f0', fontFamily: 'inherit', boxSizing: 'border-box' }}>
      {/* 헤더 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <h1 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>MLOps 대시보드</h1>
        <button onClick={handleLogout} style={{ fontSize: 10, padding: '2px 8px', background: '#1e1e2e', color: '#9ca3af', border: '1px solid #2d2d3d', borderRadius: 4, cursor: 'pointer' }}>
          로그아웃
        </button>
        <button onClick={load} style={{ fontSize: 10, padding: '2px 7px', background: '#1e1e2e', color: '#888', border: 'none', borderRadius: 4, cursor: 'pointer' }}>새로고침</button>
        <button onClick={handleTrain} disabled={trainLoading} style={{ fontSize: 10, padding: '2px 8px', background: trainLoading ? '#374151' : '#6366f1', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
          {trainLoading ? '학습중...' : '모델 재학습'}
        </button>
        {msg && <span style={{ fontSize: 10, color: '#6366f1' }}>{msg}</span>}
        {loading && <span style={{ fontSize: 10, color: '#555' }}>로딩중...</span>}
      </div>

      {/* 모델 현황 카드 */}
      {status && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8, marginBottom: 14 }}>
          {[
            { label: '모델', value: status.model_exists ? '정상' : '없음', color: status.model_exists ? '#16a34a' : '#dc2626' },
            { label: '마지막 정확도', value: status.last_accuracy != null ? `${(status.last_accuracy * 100).toFixed(1)}%` : '-', color: '#6366f1' },
            { label: '전체 신호', value: status.total_signals.toLocaleString(), color: '#e2e8f0' },
            { label: '수익률 계산됨', value: status.returns_calculated.toLocaleString(), color: '#16a34a' },
            { label: '계산 대기', value: status.pending_returns.toLocaleString(), color: status.pending_returns > 0 ? '#d97706' : '#4b5563' },
          ].map((item, i) => (
            <div key={i} style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: '10px 12px' }}>
              <div style={{ fontSize: 9, color: '#555', marginBottom: 3 }}>{item.label}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: item.color }}>{item.value}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        {/* 기간별 신호 성능 */}
        {card(
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#555' }}>신호별 성능</div>
              <div style={{ display: 'flex', gap: 3 }}>
                {[{label:'1M',days:30},{label:'3M',days:90},{label:'6M',days:180},{label:'1Y',days:365}].map(({label,days}) => (
                  <button key={days} onClick={() => setStatsDays(days)} style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, border: 'none', cursor: 'pointer', background: statsDays === days ? '#6366f1' : '#1e1e2e', color: statsDays === days ? '#fff' : '#888' }}>{label}</button>
                ))}
              </div>
            </div>
            {stats.length === 0 ? (
              <div style={{ fontSize: 11, color: '#555' }}>수익률 데이터 없음 (수익률 계산 버튼 클릭)</div>
            ) : stats.map(s => (
              <div key={s.signal} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 3, background: SIG_BG[s.signal], color: SIG_COLOR[s.signal] }}>{s.signal}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: s.accuracy >= 60 ? '#16a34a' : s.accuracy >= 50 ? '#d97706' : '#dc2626' }}>{s.accuracy.toFixed(1)}%</span>
                </div>
                <div style={{ height: 4, background: '#1e1e2e', borderRadius: 2, marginBottom: 3 }}>
                  <div style={{ height: 4, width: `${s.accuracy}%`, background: SIG_COLOR[s.signal], borderRadius: 2 }} />
                </div>
                <div style={{ fontSize: 9, color: '#555', display: 'flex', gap: 8 }}>
                  <span>{s.correct}/{s.total}건</span>
                  <span>1일: {s.avg_ret_1d >= 0 ? '+' : ''}{s.avg_ret_1d.toFixed(1)}%</span>
                  <span>5일: {s.avg_ret_5d >= 0 ? '+' : ''}{s.avg_ret_5d.toFixed(1)}%</span>
                  <span>20일: {s.avg_ret_20d >= 0 ? '+' : ''}{s.avg_ret_20d.toFixed(1)}%</span>
                </div>
              </div>
            ))}
          </>
        )}

        {/* 학습 이력 */}
        {card(
          <>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#555', marginBottom: 8 }}>학습 이력</div>
            {history.length === 0 ? (
              <div style={{ fontSize: 11, color: '#555' }}>없음</div>
            ) : history.map((h, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #13131e', fontSize: 10 }}>
                <div>
                  <span style={{ color: '#9ca3af' }}>{h.trained_at ? new Date(h.trained_at).toLocaleDateString('ko-KR') : '-'}</span>
                  <span style={{ color: '#4b5563', marginLeft: 6 }}>{h.triggered_by}</span>
                </div>
                <div>
                  <span style={{ color: '#6366f1', fontWeight: 600 }}>{(h.accuracy * 100).toFixed(1)}%</span>
                  <span style={{ color: '#4b5563', marginLeft: 5 }}>{h.stocks_used}종목</span>
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      {/* 월별 성능 */}
      {card(
        <>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#555', marginBottom: 8 }}>월별 성능 ({monthKeys.length}개월)</div>
          {monthKeys.length === 0 ? (
            <div style={{ fontSize: 11, color: '#555' }}>월별 집계 없음 (수익률 계산 후 자동 생성)</div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
                <thead>
                  <tr style={{ color: '#555', borderBottom: '1px solid #1e1e2e' }}>
                    <th style={{ textAlign: 'left', padding: '3px 6px' }}>월</th>
                    {['매수', '매도', '관망'].map(s => (
                      <React.Fragment key={s}>
                        <th style={{ textAlign: 'center', padding: '3px 6px', color: SIG_COLOR[s] }}>{s} 승률</th>
                        <th style={{ textAlign: 'center', padding: '3px 6px', color: SIG_COLOR[s] }}>{s} 5일평균</th>
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {monthKeys.map(month => {
                    const g = monthlyGrouped[month];
                    return (
                      <tr key={month} style={{ borderBottom: '1px solid #13131e' }}>
                        <td style={{ padding: '4px 6px', color: '#9ca3af' }}>{month}</td>
                        {['매수', '매도', '관망'].map(s => {
                          const d = g[s];
                          return (
                            <React.Fragment key={s}>
                              <td style={{ textAlign: 'center', padding: '4px 6px', color: d ? (d.accuracy >= 60 ? '#16a34a' : d.accuracy >= 50 ? '#d97706' : '#dc2626') : '#4b5563' }}>
                                {d ? `${d.accuracy.toFixed(0)}% (${d.correct}/${d.total})` : '-'}
                              </td>
                              <td style={{ textAlign: 'center', padding: '4px 6px' }}>
                                {d ? fmtRet(d.avg_ret_5d) : <span style={{ color: '#4b5563' }}>-</span>}
                              </td>
                            </React.Fragment>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>,
        { marginBottom: 12 }
      )}

      {/* 최근 신호 목록 */}
      {card(
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#555' }}>최근 신호</div>
            <div style={{ display: 'flex', gap: 3 }}>
              {[{label:'전체',val:''},{label:'매수',val:'매수'},{label:'매도',val:'매도'},{label:'관망',val:'관망'}].map(({label,val}) => (
                <button key={val} onClick={() => setSignalFilter(val)} style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, border: 'none', cursor: 'pointer', background: signalFilter === val ? '#6366f1' : '#1e1e2e', color: signalFilter === val ? '#fff' : '#888' }}>{label}</button>
              ))}
              {[{label:'1M',days:30},{label:'3M',days:90},{label:'6M',days:180},{label:'1Y',days:365}].map(({label,days}) => (
                <button key={days} onClick={() => setRecentDays(days)} style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, border: 'none', cursor: 'pointer', background: recentDays === days ? '#374151' : '#1e1e2e', color: recentDays === days ? '#fff' : '#888' }}>{label}</button>
              ))}
            </div>
          </div>
          <div style={{ overflowY: 'auto', maxHeight: 280 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
              <thead>
                <tr style={{ color: '#555', borderBottom: '1px solid #1e1e2e' }}>
                  {['종목', '신호', '예측일', '종가', '1일', '5일', '20일', '적중'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '3px 5px', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recent.map((r, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #13131e' }}>
                    <td style={{ padding: '3px 5px', color: '#d1d5db' }}>{r.stock_name}</td>
                    <td style={{ padding: '3px 5px' }}>
                      <span style={{ background: SIG_BG[r.signal], color: SIG_COLOR[r.signal], padding: '1px 4px', borderRadius: 3, fontWeight: 700 }}>{r.signal}</span>
                    </td>
                    <td style={{ padding: '3px 5px', color: '#6b7280' }}>{fmtDate(r.predicted_at)}</td>
                    <td style={{ padding: '3px 5px', color: '#9ca3af' }}>{r.close?.toLocaleString() ?? '-'}</td>
                    <td style={{ padding: '3px 5px' }}>{fmtRet(r.ret_1d)}</td>
                    <td style={{ padding: '3px 5px' }}>{fmtRet(r.ret_5d)}</td>
                    <td style={{ padding: '3px 5px' }}>{fmtRet(r.ret_20d)}</td>
                    <td style={{ padding: '3px 5px' }}>
                      {r.is_correct_5d == null ? <span style={{ color: '#4b5563' }}>대기</span>
                        : r.is_correct_5d ? <span style={{ color: '#16a34a' }}>O</span>
                          : <span style={{ color: '#dc2626' }}>X</span>}
                    </td>
                  </tr>
                ))}
                {recent.length === 0 && (
                  <tr><td colSpan={8} style={{ padding: 10, color: '#555', textAlign: 'center' }}>데이터 없음</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
};

export default MLOpsDashboard;
