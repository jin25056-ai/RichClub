import React, { useState, useEffect } from 'react';
import apiClient from '../api/client';

interface ModelStatus {
  model_exists: boolean;
  model_path: string;
  last_trained_at: string | null;
  last_accuracy: number | null;
  total_predictions: number;
  pending_evaluation: number;
}

interface TrainHistory {
  trained_at: string;
  triggered_by: string;
  accuracy: number;
  n_train: number;
  n_test: number;
  elapsed_sec: number;
  stocks_used: number;
  label_dist: Record<string, number>;
}

interface PredictionStats {
  signal: string;
  total: number;
  evaluated: number;
  correct: number;
  accuracy: number;
  avg_return_pct: number;
}

interface RecentPrediction {
  stock_name: string;
  stock_code: string;
  signal: string;
  predicted_at: string;
  close_at_prediction: number | null;
  actual_return_pct: number | null;
  is_correct: boolean | null;
  evaluated: boolean;
}

const SIGNAL_COLOR: Record<string, string> = { 매수: '#16a34a', 매도: '#dc2626', 관망: '#d97706' };
const SIGNAL_BG: Record<string, string> = { 매수: '#14532d', 매도: '#7f1d1d', 관망: '#78350f' };

const fmt = (v: number | null) => v != null ? v.toFixed(2) : '-';
const fmtDate = (s: string | null) => {
  if (!s) return '-';
  return new Date(s).toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
};

const MLOpsDashboard: React.FC = () => {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [history, setHistory] = useState<TrainHistory[]>([]);
  const [stats, setStats] = useState<PredictionStats[]>([]);
  const [recent, setRecent] = useState<RecentPrediction[]>([]);
  const [statsDays, setStatsDays] = useState(30);
  const [recentDays, setRecentDays] = useState(7);
  const [signalFilter, setSignalFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [trainLoading, setTrainLoading] = useState(false);
  const [msg, setMsg] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [s, h, st, r] = await Promise.all([
        apiClient.get<ModelStatus>('/api/v1/mlops/status'),
        apiClient.get<TrainHistory[]>('/api/v1/mlops/train-history'),
        apiClient.get<PredictionStats[]>(`/api/v1/mlops/prediction-stats?days=${statsDays}`),
        apiClient.get<RecentPrediction[]>(`/api/v1/mlops/recent-predictions?days=${recentDays}${signalFilter ? `&signal=${signalFilter}` : ''}`),
      ]);
      setStatus(s.data);
      setHistory(h.data);
      setStats(st.data);
      setRecent(r.data);
    } catch (e) {
      setMsg('데이터 로드 실패');
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, [statsDays, recentDays, signalFilter]);

  const handleTrain = async () => {
    setTrainLoading(true);
    setMsg('');
    try {
      const res = await apiClient.post('/api/v1/mlops/train');
      setMsg(`학습 완료: 정확도 ${(res.data.accuracy * 100).toFixed(1)}%, ${res.data.n_samples}건, ${res.data.elapsed_sec}초`);
      load();
    } catch (e) {
      setMsg('학습 실패');
    }
    setTrainLoading(false);
  };

  const handleEvaluate = async () => {
    try {
      await apiClient.post('/api/v1/mlops/evaluate');
      setMsg('평가 완료');
      load();
    } catch (e) {
      setMsg('평가 실패');
    }
  };

  const card = (children: React.ReactNode, style?: React.CSSProperties) => (
    <div style={{
      background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 8,
      padding: '14px 16px', ...style
    }}>{children}</div>
  );

  const label = (text: string) => (
    <div style={{ fontSize: 11, fontWeight: 600, color: '#555', marginBottom: 8 }}>{text}</div>
  );

  return (
    <div style={{
      background: '#0a0a14', minHeight: '100vh', padding: '16px 20px',
      fontFamily: 'inherit', color: '#e2e8f0', boxSizing: 'border-box',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <h1 style={{ fontSize: 16, fontWeight: 700, color: '#e2e8f0', margin: 0 }}>MLOps 대시보드</h1>
        <button onClick={load} style={{ fontSize: 10, padding: '3px 8px', background: '#1e1e2e', color: '#888', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
          새로고침
        </button>
        <button onClick={handleTrain} disabled={trainLoading}
          style={{ fontSize: 10, padding: '3px 10px', background: trainLoading ? '#374151' : '#6366f1', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
          {trainLoading ? '학습 중...' : '수동 재학습'}
        </button>
        <button onClick={handleEvaluate}
          style={{ fontSize: 10, padding: '3px 10px', background: '#1e1e2e', color: '#9ca3af', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
          성능 평가 실행
        </button>
        {msg && <span style={{ fontSize: 11, color: '#6366f1' }}>{msg}</span>}
      </div>

      {loading && <div style={{ fontSize: 11, color: '#555', marginBottom: 12 }}>불러오는 중...</div>}

      {/* 모델 현황 */}
      {status && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 16 }}>
          {[
            { label: '모델 상태', value: status.model_exists ? '정상' : '없음', color: status.model_exists ? '#16a34a' : '#dc2626' },
            { label: '마지막 정확도', value: status.last_accuracy != null ? `${(status.last_accuracy * 100).toFixed(1)}%` : '-', color: '#6366f1' },
            { label: '누적 예측', value: `${status.total_predictions.toLocaleString()}건`, color: '#e2e8f0' },
            { label: '평가 대기', value: `${status.pending_evaluation.toLocaleString()}건`, color: status.pending_evaluation > 100 ? '#d97706' : '#6b7280' },
          ].map((item) => card(
            <>
              <div style={{ fontSize: 9, color: '#555', marginBottom: 4 }}>{item.label}</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: item.color }}>{item.value}</div>
              {item.label === '모델 상태' && status.last_trained_at && (
                <div style={{ fontSize: 9, color: '#4b5563', marginTop: 3 }}>
                  마지막 학습: {fmtDate(status.last_trained_at)}
                </div>
              )}
            </>,
            {}
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
        {/* 신호별 정확도 */}
        {card(
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              {label('신호별 예측 성능')}
              <div style={{ display: 'flex', gap: 4 }}>
                {[7, 14, 30, 90].map((d) => (
                  <button key={d} onClick={() => setStatsDays(d)}
                    style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, border: 'none', cursor: 'pointer', background: statsDays === d ? '#6366f1' : '#1e1e2e', color: statsDays === d ? '#fff' : '#888' }}>
                    {d}일
                  </button>
                ))}
              </div>
            </div>
            {stats.length === 0 ? (
              <div style={{ fontSize: 11, color: '#555' }}>평가된 예측 없음</div>
            ) : stats.map((s) => (
              <div key={s.signal} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 3,
                    background: SIGNAL_BG[s.signal], color: SIGNAL_COLOR[s.signal],
                  }}>{s.signal}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: s.accuracy >= 60 ? '#16a34a' : s.accuracy >= 50 ? '#d97706' : '#dc2626' }}>
                    {s.accuracy.toFixed(1)}%
                  </span>
                </div>
                <div style={{ height: 4, background: '#1e1e2e', borderRadius: 2 }}>
                  <div style={{ height: 4, width: `${s.accuracy}%`, background: SIGNAL_COLOR[s.signal], borderRadius: 2 }} />
                </div>
                <div style={{ display: 'flex', gap: 10, marginTop: 3, fontSize: 9, color: '#555' }}>
                  <span>{s.correct}승 {s.total - s.correct}패 ({s.total}건)</span>
                  <span>평균 수익 {s.avg_return_pct >= 0 ? '+' : ''}{s.avg_return_pct.toFixed(2)}%</span>
                </div>
              </div>
            ))}
          </>
        )}

        {/* 학습 이력 */}
        {card(
          <>
            {label('학습 이력')}
            <div style={{ overflowY: 'auto', maxHeight: 200 }}>
              {history.length === 0 ? (
                <div style={{ fontSize: 11, color: '#555' }}>학습 이력 없음</div>
              ) : history.map((h, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '5px 0', borderBottom: '1px solid #13131e', fontSize: 10,
                }}>
                  <div>
                    <span style={{ color: '#9ca3af' }}>{fmtDate(h.trained_at)}</span>
                    <span style={{ color: '#4b5563', marginLeft: 8 }}>{h.triggered_by}</span>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ color: '#6366f1', fontWeight: 600 }}>{(h.accuracy * 100).toFixed(1)}%</span>
                    <span style={{ color: '#4b5563', marginLeft: 6 }}>{h.stocks_used}종목</span>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* 최근 예측 목록 */}
      {card(
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            {label('최근 예측 목록')}
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              {['', '매수', '매도', '관망'].map((s) => (
                <button key={s} onClick={() => setSignalFilter(s)}
                  style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, border: 'none', cursor: 'pointer', background: signalFilter === s ? '#6366f1' : '#1e1e2e', color: signalFilter === s ? '#fff' : '#888' }}>
                  {s || '전체'}
                </button>
              ))}
              {[3, 7, 14].map((d) => (
                <button key={d} onClick={() => setRecentDays(d)}
                  style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, border: 'none', cursor: 'pointer', background: recentDays === d ? '#374151' : '#1e1e2e', color: recentDays === d ? '#fff' : '#888' }}>
                  {d}일
                </button>
              ))}
            </div>
          </div>
          <div style={{ overflowY: 'auto', maxHeight: 300 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
              <thead>
                <tr style={{ color: '#555', borderBottom: '1px solid #1e1e2e' }}>
                  {['종목', '코드', '신호', '예측일', '예측 종가', '실제 수익', '결과'].map((h) => (
                    <th key={h} style={{ textAlign: 'left', padding: '4px 6px', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recent.map((r, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #13131e' }}>
                    <td style={{ padding: '4px 6px', color: '#d1d5db' }}>{r.stock_name}</td>
                    <td style={{ padding: '4px 6px', color: '#4b5563' }}>{r.stock_code}</td>
                    <td style={{ padding: '4px 6px' }}>
                      <span style={{ background: SIGNAL_BG[r.signal], color: SIGNAL_COLOR[r.signal], padding: '1px 5px', borderRadius: 3, fontWeight: 700 }}>
                        {r.signal}
                      </span>
                    </td>
                    <td style={{ padding: '4px 6px', color: '#6b7280' }}>{fmtDate(r.predicted_at)}</td>
                    <td style={{ padding: '4px 6px', color: '#9ca3af' }}>
                      {r.close_at_prediction != null ? r.close_at_prediction.toLocaleString() : '-'}
                    </td>
                    <td style={{ padding: '4px 6px', color: r.actual_return_pct != null ? (r.actual_return_pct >= 0 ? '#16a34a' : '#dc2626') : '#4b5563' }}>
                      {r.actual_return_pct != null ? `${r.actual_return_pct >= 0 ? '+' : ''}${r.actual_return_pct.toFixed(2)}%` : '-'}
                    </td>
                    <td style={{ padding: '4px 6px' }}>
                      {!r.evaluated ? (
                        <span style={{ color: '#4b5563' }}>대기</span>
                      ) : r.is_correct ? (
                        <span style={{ color: '#16a34a' }}>적중</span>
                      ) : (
                        <span style={{ color: '#dc2626' }}>미적중</span>
                      )}
                    </td>
                  </tr>
                ))}
                {recent.length === 0 && (
                  <tr><td colSpan={7} style={{ padding: 12, color: '#555', textAlign: 'center' }}>데이터 없음</td></tr>
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
