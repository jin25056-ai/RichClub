import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Bar, Cell, Legend,
} from 'recharts';
import { stockApi, StockItem } from '../../api/stock';

type Period = '1m' | '3m' | '6m';
type ChartInterval = '1d' | '5m';

const Y_AXIS_WIDTH = 58;
const SYNC_ID = 'stock-sync';
const MARGIN = { left: 0, right: 10, top: 4, bottom: 0 };
const PERIOD_EXTRA = 60;
const ICHIMOKU_SHIFT = 26;

const getChartHeights = () => {
  const available = window.innerHeight - 56 - 20 - 20 - 80;
  return {
    candle: Math.floor(available * 0.52),
    macd:   Math.floor(available * 0.24),
    rsi:    Math.floor(available * 0.24),
  };
};

const calcMA = (data: any[], n: number): (number | null)[] =>
  data.map((_, i) => {
    if (i < n - 1) return null;
    const vals = data.slice(i - n + 1, i + 1).map((d) => d.close).filter((v) => v != null);
    if (vals.length < n) return null;
    return Math.round(vals.reduce((s, v) => s + v, 0) / n);
  });

const calcIchimoku = (data: any[]) => {
  const hi = (i: number, n: number) =>
    Math.max(...data.slice(Math.max(0, i - n + 1), i + 1).map((d) => d.high ?? -Infinity));
  const lo = (i: number, n: number) =>
    Math.min(...data.slice(Math.max(0, i - n + 1), i + 1).map((d) => d.low ?? Infinity));
  return data.map((_, i) => ({
    tenkan: i >= 8  ? Math.round((hi(i, 9)  + lo(i, 9))  / 2) : null,
    kijun:  i >= 25 ? Math.round((hi(i, 26) + lo(i, 26)) / 2) : null,
    spanA:  i >= 8 && i >= 25 ? Math.round(((hi(i, 9) + lo(i, 9)) / 2 + (hi(i, 26) + lo(i, 26)) / 2) / 2) : null,
    spanB:  i >= 51 ? Math.round((hi(i, 52) + lo(i, 52)) / 2) : null,
  }));
};

// 변곡 주기 후보
const INFLECTION_CANDIDATES = [12, 13, 17, 26, 34, 42, 52, 66, 77, 88, 100];

// 변곡 주기 자동 탐지: 극값(고점/저점) 간 봉 간격 분석
const calcInflectionCycle = (data: any[]): number => {
  if (data.length < 20) return 26;
  const closes = data.map((d) => d.close).filter((v) => v != null) as number[];
  const wing = 5;
  const pivots: number[] = [];
  for (let i = wing; i < closes.length - wing; i++) {
    const slice = closes.slice(i - wing, i + wing + 1);
    const max = Math.max(...slice);
    const min = Math.min(...slice);
    if (closes[i] === max || closes[i] === min) pivots.push(i);
  }
  if (pivots.length < 3) return 26;
  const gaps: number[] = [];
  for (let i = 1; i < pivots.length; i++) gaps.push(pivots[i] - pivots[i - 1]);
  const scores: Record<number, number> = {};
  for (const cand of INFLECTION_CANDIDATES) {
    scores[cand] = gaps.filter((g) => {
      const mod = g % cand;
      return mod <= 3 || mod >= cand - 3;
    }).length;
  }
  const best = INFLECTION_CANDIDATES.reduce((a, b) => scores[a] >= scores[b] ? a : b);
  return scores[best] >= 2 ? best : 26;
};

// 변곡 주기 세트 (탐지된 기본 주기에 따라 이후 변곡 간격 정의)
const INFLECTION_SETS: Record<number, number[]> = {
  12:  [12, 26, 52, 66, 77, 88, 100],
  13:  [13, 26, 52, 66, 77, 88, 100],
  17:  [17, 34, 42, 52, 66, 77, 88, 100],
  26:  [26, 52, 66, 77, 88, 100],
  34:  [34, 52, 66, 77, 88, 100],
  42:  [42, 52, 66, 77, 88, 100],
  52:  [52, 66, 77, 88, 100],
  66:  [66, 77, 88, 100],
  77:  [77, 88, 100],
  88:  [88, 100],
  100: [100],
};

// 변곡선 날짜 목록 계산
// 모든 극값을 시작점으로 잡고, 해당 세트 간격마다 변곡선 생성
const calcInflectionLines = (data: any[], cycle: number): { date: string; isFuture: boolean }[] => {
  if (data.length < cycle) return [];
  const closes = data.map((d) => d.close) as (number | null)[];
  const wing = Math.max(3, Math.floor(cycle / 4));

  // 모든 극값 탐지
  const pivots: number[] = [];
  for (let i = wing; i < closes.length - wing; i++) {
    const c = closes[i];
    if (c == null) continue;
    const slice = closes.slice(i - wing, i + wing + 1).filter((v) => v != null) as number[];
    if (c === Math.max(...slice) || c === Math.min(...slice)) pivots.push(i);
  }
  if (pivots.length === 0) return [];

  const set = INFLECTION_SETS[cycle] ?? [cycle];
  const lineSet = new Set<string>();
  const today = data[data.length - 1]?.datetime ?? '';

  for (const pivotIdx of pivots) {
    for (const offset of set) {
      const idx = pivotIdx + offset;
      if (idx < data.length) {
        lineSet.add(data[idx].datetime + ':past');
      } else {
        // 미래 날짜 추정
        const remaining = idx - (data.length - 1);
        const d = new Date(data[data.length - 1].datetime);
        let added = 0;
        while (added < remaining) {
          d.setDate(d.getDate() + 1);
          if (d.getDay() !== 0 && d.getDay() !== 6) added++;
        }
        lineSet.add(d.toISOString().slice(0, 10) + ':future');
      }
    }
  }

  // 중복 제거 후 날짜순 정렬, 미래는 3개만
  const past: { date: string; isFuture: boolean }[] = [];
  const future: { date: string; isFuture: boolean }[] = [];
  Array.from(lineSet).forEach((key) => {
    const [date, type] = key.split(':');
    if (type === 'future') future.push({ date, isFuture: true });
    else past.push({ date, isFuture: false });
  });
  future.sort((a, b) => a.date.localeCompare(b.date));
  return [...past, ...future.slice(0, 3)];
};

// 골든보 감지: MA60 우상향 중 캔들이 MA60에 U자로 지지받고 반등하는 시점
// 추가 조건: MACD가 시그널 위(매수 우호)여야 함
const calcGoldenBo = (data: any[]): Set<string> => {
  const result = new Set<string>();
  const N = 20;
  for (let i = N; i < data.length; i++) {
    const cur = data[i];
    const prev = data[i - 1];
    if (!cur.ma60 || !prev.ma60 || !cur.close) continue;
    if (cur.ma60 <= prev.ma60) continue;
    if (cur.close < cur.ma60) continue;
    // MACD 매수 우호 조건 추가
    if (cur.macd == null || cur.macdSignal == null || cur.macd <= cur.macdSignal) continue;
    const window = data.slice(i - N, i);
    const touchedBelow = window.some((d: any) =>
      d.close != null && d.ma60 != null && d.close < d.ma60 * 1.01
    );
    if (!touchedBelow) continue;
    if (prev.close != null && prev.ma60 != null && prev.close < prev.ma60 * 1.02) {
      result.add(cur.datetime);
    }
  }
  return result;
};

const SIGNAL_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  매수: { label: 'BUY',  color: '#fff', bg: '#16a34a' },
  매도: { label: 'SELL', color: '#fff', bg: '#dc2626' },
};
const SIMPLE_SELL_BADGE = { label: 'SELL', color: '#d97706', bg: '#78350f55' };

const makeCandleShape = (domainMin: number, domainMax: number) => (props: any) => {
  const { x, y, width, height, payload } = props;
  if (!payload || payload.open == null || payload.close == null) return null;
  if (y == null || height == null || !width || height === 0) return null;
  const { open, high, low, close, aiSignal, simpleSell, goldenBo } = payload;
  const isUp = close >= open;
  const color = isUp ? '#16a34a' : '#dc2626';
  const domainMinPixel = y + height;
  const pixelPerUnit = height / (close - domainMin);
  const toY = (v: number) => domainMinPixel - (v - domainMin) * pixelPerUnit;
  const openY = toY(open); const closeY = toY(close);
  const highY = toY(high ?? Math.max(open, close));
  const lowY  = toY(low  ?? Math.min(open, close));
  const bodyTop = Math.min(openY, closeY);
  const bodyH   = Math.max(Math.abs(openY - closeY), 1);
  const bw = Math.max(width - 2, 2); const cx = x + width / 2;
  const b = aiSignal && SIGNAL_BADGE[aiSignal] ? SIGNAL_BADGE[aiSignal] : null;
  const showSimpleSell = simpleSell && !b;
  return (
    <g>
      {goldenBo && (
        <rect x={cx - bw} y={highY - 6} width={bw * 2} height={lowY - highY + 6}
          fill="#f0abfc" fillOpacity={0.08} rx={1} />
      )}
      <line x1={cx} y1={highY} x2={cx} y2={bodyTop} stroke={color} strokeWidth={1.5} />
      <line x1={cx} y1={bodyTop + bodyH} x2={cx} y2={lowY} stroke={color} strokeWidth={1.5} />
      <rect x={cx - bw / 2} y={bodyTop} width={bw} height={bodyH} fill={color} stroke={color} strokeWidth={1} />
      {goldenBo && (
        <g>
          <rect x={cx - 16} y={lowY + 3} width={32} height={11} rx={2} fill="#7e22ce" />
          <text x={cx} y={lowY + 11} textAnchor="middle" fontSize={6} fontWeight="700" fill="#f0abfc">골든보</text>
        </g>
      )}
      {b && aiSignal === '매도' && (
        <g>
          <rect x={cx - 12} y={highY - 14} width={24} height={11} rx={2} fill={b.bg} />
          <text x={cx} y={highY - 6} textAnchor="middle" fontSize={6} fontWeight="700" fill={b.color}>SELL</text>
        </g>
      )}
      {b && aiSignal === '매수' && (
        <g>
          <rect x={cx - 12} y={lowY + 3} width={24} height={11} rx={2} fill={b.bg} />
          <text x={cx} y={lowY + 11} textAnchor="middle" fontSize={6} fontWeight="700" fill={b.color}>{b.label}</text>
        </g>
      )}
      {showSimpleSell && (
        <g>
          <rect x={cx - 12} y={highY - 14} width={24} height={11} rx={2} fill={SIMPLE_SELL_BADGE.bg} stroke="#d97706" strokeWidth={0.5} />
          <text x={cx} y={highY - 6} textAnchor="middle" fontSize={6} fontWeight="700" fill={SIMPLE_SELL_BADGE.color}>{SIMPLE_SELL_BADGE.label}</text>
        </g>
      )}
    </g>
  );
};

const TIP = { background: '#12121f', border: '1px solid #2d2d3d', borderRadius: 6, padding: '7px 10px', fontSize: 11, minWidth: 140 };

const tipRow = (lbl: string, val: any, color = '#e2e8f0') => val != null ? (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
    <span style={{ color: '#777' }}>{lbl}</span>
    <span style={{ color, fontWeight: 500 }}>{val}</span>
  </div>
) : null;

const fmt = (v: any) => v != null ? Math.round(v).toLocaleString() : null;

const bdg = (label: string, color: string) => (
  <span key={label} style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: color + '22', color, border: '1px solid ' + color + '55', fontWeight: 600 }}>
    {label}
  </span>
);

const tipHeader = (label: string, ...badges: (React.ReactElement | null)[]) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4, gap: 6 }}>
    <span style={{ color: '#6366f1', fontWeight: 600 }}>{label}</span>
    <span style={{ display: 'flex', gap: 4 }}>{badges.filter(Boolean)}</span>
  </div>
);

const getCompositeSignal = (d: any) => {
  if (!d) return null;
  if (d.goldenBo) return { label: '골든보', sub: 'MA60 U자 지지 반등', color: '#f0abfc', goldenBo: true };
  if (d.ichimokuStagnant) return { label: '침체(일목)', sub: '선행스팬 역배열+스팬A 아래', color: '#6b7280', stagnant: true };
  if (d.ma60Falling) return { label: '침체(MA60)', sub: 'MA60 하락중 매수금지', color: '#6b7280', stagnant: true };
  if (d.ma60Turning) return { label: 'MA60 턴', sub: '60일선 반등 - 매수 타이밍', color: '#f0abfc', turning: true };
  if (d.rsiBreakDown) return { label: '강한 매도', sub: 'RSI 70 하방이탈', color: '#dc2626' };

  // 음봉 여부
  const isBearCandle = d.open != null && d.close != null && d.close < d.open;

  let bull = 0; let bear = 0;
  if (d.ma5 != null && d.ma20 != null && d.ma60 != null) {
    if (d.ma5 > d.ma20 && d.ma20 > d.ma60) bull++;
    else if (d.ma5 < d.ma20 && d.ma20 < d.ma60) bear++;
  }
  if (d.macd != null && d.macdSignal != null) {
    if (d.macd > d.macdSignal) bull++;
    else if (d.macd < d.macdSignal) bear++;
  }
  if (d.rsi != null) {
    if (d.rsi <= 30) bull++;
    else if (d.rsi >= 70) bear++;
    else bull += 0.5;
  }
  const score = bull - bear;

  // 음봉이면 매수 신호 억제
  if (isBearCandle) {
    if (score <= -1) return { label: '강한 매도', sub: '3개 지표 매도', color: '#dc2626' };
    if (score < 0)   return { label: '매도 우세', sub: '2개 지표 매도', color: '#f87171' };
    return { label: '음봉 주의', sub: '지표 매수지만 음봉 - 매수금지', color: '#f59e0b', bearCandle: true };
  }

  if (score >= 2.5) return { label: '강한 매수', sub: '3개 지표 매수', color: '#16a34a' };
  if (score >= 1.5) return { label: '매수 우세', sub: '2개 지표 매수', color: '#4ade80' };
  if (score <= -2)  return { label: '강한 매도', sub: '3개 지표 매도', color: '#dc2626' };
  if (score <= -1)  return { label: '매도 우세', sub: '2개 지표 매도', color: '#f87171' };
  return { label: '중립', sub: '지표 혼재', color: '#6b7280' };
};

const CandleTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d || d.open == null) return null;
  const maState = d.ma5 != null && d.ma20 != null && d.ma60 != null
    ? d.ma5 > d.ma20 && d.ma20 > d.ma60 ? bdg('정배열', '#16a34a')
    : d.ma5 < d.ma20 && d.ma20 < d.ma60 ? bdg('역배열', '#dc2626')
    : null : null;
  const crossBadge = d.goldenCross ? bdg('골든크로스', '#facc15')
    : d.deadCross ? bdg('데드크로스', '#a855f7')
    : null;
  const composite = getCompositeSignal(d);
  return (
    <div style={TIP}>
      {tipHeader(label, maState, crossBadge)}
      {composite && (
        <div style={{ margin: '4px 0 6px', padding: '4px 8px', borderRadius: 4, background: composite.color + '18', border: '1px solid ' + composite.color + '44', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: composite.color }}>{composite.label}</span>
          <span style={{ fontSize: 9, color: composite.color + 'cc' }}>{composite.sub}</span>
        </div>
      )}
      {(composite as any)?.goldenBo && (
        <div style={{ fontSize: 9, color: '#f0abfc', fontWeight: 600, marginBottom: 4 }}>MA60 U자 지지 - 강한 매수 타이밍</div>
      )}
      {(composite as any)?.bearCandle && (
        <div style={{ fontSize: 9, color: '#f59e0b', fontWeight: 600, marginBottom: 4 }}>음봉 마감 - 지표 매수지만 진입 금지</div>
      )}
      {(composite as any)?.stagnant && (
        <div style={{ fontSize: 9, color: '#6b7280', marginBottom: 4 }}>MA60 하락 구간 - 매수/매도 금지</div>
      )}
      {(composite as any)?.turning && (
        <div style={{ fontSize: 9, color: '#f0abfc', fontWeight: 600, marginBottom: 4 }}>MA60 반등 전환점 - 매수 타이밍</div>
      )}
      {tipRow('시가', fmt(d.open))}
      {tipRow('고가', fmt(d.high), '#16a34a')}
      {tipRow('저가', fmt(d.low), '#dc2626')}
      {tipRow('종가', fmt(d.close))}
      {d.ma5 != null && <div style={{ marginTop: 4 }}>
        {tipRow('MA5',  fmt(d.ma5),  '#facc15')}
        {tipRow('MA20', fmt(d.ma20), '#fb923c')}
        {d.ma60 != null && tipRow('MA60', fmt(d.ma60), '#a78bfa')}
      </div>}
    </div>
  );
};

const RsiTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d || d.rsi == null) return null;
  const rsi = d.rsi;
  const rsiBreak = d.rsiBreakDown ? bdg('매도!', '#dc2626') : null;
  const rsiLevel = rsi >= 70 ? bdg('과매수', '#f97316')
    : rsi <= 30 ? bdg('과매도', '#16a34a')
    : null;
  return (
    <div style={TIP}>
      {tipHeader(label, rsiBreak, rsiLevel)}
      {tipRow('RSI', rsi?.toFixed(2), '#6366f1')}
      {d.rsiBreakDown && (
        <div style={{ marginTop: 4, fontSize: 9, color: '#dc2626', fontWeight: 600 }}>RSI 70 하방이탈 - 매도 신호</div>
      )}
    </div>
  );
};

const MacdTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d || d.macd == null) return null;
  const hist = d.histogram ?? 0;
  const macdBadge = d.macd > d.macdSignal
    ? bdg('MACD 위 (매수 우호)', '#16a34a')
    : d.macd < d.macdSignal
    ? bdg('시그널 위 (매도 우호)', '#dc2626')
    : null;
  return (
    <div style={TIP}>
      {tipHeader(label, macdBadge)}
      {tipRow('MACD',      fmt(d.macd),      '#6366f1')}
      {tipRow('시그널',    fmt(d.macdSignal), '#f59e0b')}
      {tipRow('히스토그램', fmt(d.histogram),  hist >= 0 ? '#16a34a' : '#dc2626')}
    </div>
  );
};

interface Props {
  initialStock?: { code: string; name: string } | null;
  onStockChange?: (code: string, name: string) => void;
  searchOnly?: boolean;
  chartOnly?: boolean;
  period?: Period;
  sellMode?: 'ai' | 'simple';
  chartInterval?: ChartInterval;
  onPriceUpdate?: (price: number) => void;
  modelId?: string;
}

const StockSearchSection: React.FC<Props> = ({ initialStock, onStockChange, searchOnly, chartOnly, period: externalPeriod, sellMode = 'ai', chartInterval: externalInterval, onPriceUpdate, modelId = 'ju-model-v2' }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StockItem[]>([]);
  const [selected, setSelected] = useState<StockItem | null>(null);
  const [period, setPeriod] = useState<Period>('3m');
  const [chartInterval, setChartInterval] = useState<ChartInterval>('1d');
  const [chartData, setChartData] = useState<any[]>([]);
  const [rawData, setRawData] = useState<{ trimmed: any[]; futurePadding: any[]; sigMap: Record<string, string> } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [heights, setHeights] = useState(getChartHeights());
  const [viewRange, setViewRange] = useState<[number, number] | null>(null);
  const [inflectionLines, setInflectionLines] = useState<{ date: string; isFuture: boolean }[]>([]);
  const [inflectionCycle, setInflectionCycle] = useState<number>(0);
  // 변곡 설정 모드: null=비활성, 'start'=시작점 선택중, 'end'=끝점 선택중
  const [inflectionMode, setInflectionMode] = useState<null | 'start' | 'end'>(null);
  const [inflectionStart, setInflectionStart] = useState<string | null>(null);
  const [inflectionEnd, setInflectionEnd] = useState<string | null>(null);
  const chartWrapRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; startRange: [number, number] } | null>(null);
  const isDragging = useRef(false);
  const skipSearch = useRef(false);

  useEffect(() => {
    const onResize = () => setHeights(getChartHeights());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    if (!rawData) return;
    const { trimmed, futurePadding, sigMap } = rawData;
    const all = [...trimmed, ...futurePadding];

    // 변곡 주기 계산 (전체 sorted 기준)
    const cycle = calcInflectionCycle(trimmed);
    setInflectionCycle(cycle);
    const lines = calcInflectionLines(all, cycle);
    setInflectionLines(lines);

    // 골든보 감지
    const goldenBoSet = calcGoldenBo(trimmed);

    const finalData = all.map((row, i) => {
      const prev = i > 0 ? all[i - 1] : null;
      const simpleSell = sellMode === 'simple' && row.ma5 != null && prev?.ma5 != null && row.ma5 < prev.ma5;
      const goldenCross = prev?.ma5 != null && prev?.ma20 != null && row.ma5 != null && row.ma20 != null
        && prev.ma5 < prev.ma20 && row.ma5 > row.ma20;
      const deadCross = prev?.ma5 != null && prev?.ma20 != null && row.ma5 != null && row.ma20 != null
        && prev.ma5 > prev.ma20 && row.ma5 < row.ma20;
      const rsiBreakDown = prev?.rsi != null && row.rsi != null && prev.rsi >= 70 && row.rsi < 70;
      const ma60Falling = prev?.ma60 != null && row.ma60 != null && row.ma60 < prev.ma60;
      const prevPrev = i > 1 ? all[i - 2] : null;
      const ma60Turning = prevPrev?.ma60 != null && prev?.ma60 != null && row.ma60 != null
        && prev.ma60 < prevPrev.ma60 && row.ma60 >= prev.ma60;
      const ichimokuStagnant = row.spanA != null && row.spanB != null && row.close != null
        && row.spanA < row.spanB && row.close < row.spanA;
      // 골든보는 일목 침체 구간이 아닐 때만 유효
      const goldenBo = goldenBoSet.has(row.datetime) && !ichimokuStagnant;
      return { ...row, aiSignal: sigMap[row.datetime] ?? null, simpleSell, goldenCross, deadCross, rsiBreakDown, ma60Falling, ma60Turning, ichimokuStagnant, goldenBo };
    });
    setChartData(finalData);
    setViewRange(null);
  }, [rawData, sellMode]);

  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const total = chartData.length;
    if (total === 0) return;
    setViewRange((prev) => {
      const cur: [number, number] = prev ?? [0, total - 1];
      const [s, en] = cur;
      const span = en - s;
      if (e.shiftKey) {
        const step = Math.max(1, Math.floor(span * 0.15));
        const shift = e.deltaY > 0 ? step : -step;
        let ns = s + shift; let ne = en + shift;
        if (ns < 0) { ns = 0; ne = span; }
        if (ne >= total) { ne = total - 1; ns = ne - span; }
        return [Math.max(0, ns), ne];
      }
      const delta = e.deltaY > 0 ? 1 : -1;
      const step = Math.max(1, Math.floor(span * 0.15));
      const newSpan = Math.min(total - 1, Math.max(10, span + delta * step));
      const ratio = chartWrapRef.current
        ? Math.min(1, Math.max(0, (e.clientX - chartWrapRef.current.getBoundingClientRect().left) / chartWrapRef.current.offsetWidth))
        : 0.5;
      const anchor = Math.round(s + span * ratio);
      let ns = Math.round(anchor - newSpan * ratio);
      let ne = ns + newSpan;
      if (ns < 0) { ns = 0; ne = newSpan; }
      if (ne >= total) { ne = total - 1; ns = ne - newSpan; }
      return [Math.max(0, ns), ne];
    });
  }, [chartData.length]);

  useEffect(() => {
    const el = chartWrapRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const total = chartData.length;
    if (total === 0) return;
    const cur: [number, number] = viewRange ?? [0, total - 1];
    dragRef.current = { startX: e.clientX, startRange: cur };
    isDragging.current = false;
    let rafId: number | null = null;
    let pendingRange: [number, number] | null = null;
    const onMove = (me: MouseEvent) => {
      if (!dragRef.current || !chartWrapRef.current) return;
      const dx = me.clientX - dragRef.current.startX;
      if (Math.abs(dx) > 3) isDragging.current = true;
      if (!isDragging.current) return;
      const width = chartWrapRef.current.offsetWidth - Y_AXIS_WIDTH;
      const [s, en] = dragRef.current.startRange;
      const span = en - s;
      const shift = Math.round(-(dx / width) * span);
      let ns = s + shift; let ne = en + shift;
      if (ns < 0) { ns = 0; ne = span; }
      if (ne >= total) { ne = total - 1; ns = ne - span; }
      pendingRange = [Math.max(0, ns), ne];
      if (rafId === null) {
        rafId = requestAnimationFrame(() => {
          if (pendingRange) setViewRange(pendingRange);
          rafId = null;
        });
      }
    };
    const onUp = () => {
      dragRef.current = null;
      if (rafId !== null) cancelAnimationFrame(rafId);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  // 변곡 설정 모드에서 차트 클릭 시 날짜 선택
  const handleChartClick = useCallback((e: React.MouseEvent) => {
    if (inflectionMode === null) return;
    if (!chartWrapRef.current || !chartData.length) return;
    const rect = chartWrapRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left - Y_AXIS_WIDTH;
    const chartWidth = rect.width - Y_AXIS_WIDTH;
    if (x < 0 || x > chartWidth) return;
    const ratio = x / chartWidth;
    // viewRange 반영
    const total = chartData.length;
    const [rangeStart, rangeEnd] = viewRange ?? [0, total - 1];
    const rangeLen = rangeEnd - rangeStart;
    const idx = rangeStart + Math.round(ratio * rangeLen);
    const clamped = Math.max(0, Math.min(idx, total - 1));
    const date = chartData[clamped].datetime;
    if (inflectionMode === 'start') {
      setInflectionStart(date);
      setInflectionEnd(null);
      setInflectionMode('end');
    } else if (inflectionMode === 'end') {
      setInflectionEnd(date);
      setInflectionMode(null);
    }
  }, [inflectionMode, chartData, viewRange]);

  const handleDoubleClick = () => setViewRange(null);

  useEffect(() => {
    if (externalPeriod && externalPeriod !== period) {
      setPeriod(externalPeriod);
      if (selected) fetchAll(selected.stock_code, selected.stock_name, externalPeriod);
    }
  }, [externalPeriod]);

  useEffect(() => {
    if (initialStock) {
      const p = externalPeriod ?? period;
      if (chartOnly) {
        setSelected({ stock_code: initialStock.code, stock_name: initialStock.name });
        fetchAll(initialStock.code, initialStock.name, p);
      } else if (searchOnly) {
        skipSearch.current = true;
        setQuery('');
        setResults([]);
        setShowDropdown(false);
      } else {
        skipSearch.current = true;
        setQuery('');
        setSelected({ stock_code: initialStock.code, stock_name: initialStock.name });
        setResults([]);
        setShowDropdown(false);
        fetchAll(initialStock.code, initialStock.name, p);
      }
    }
  }, [initialStock?.code]);

  const handleSearch = () => {
    if (!query.trim()) return;
    stockApi.search(query).then((res) => { setResults(res.data); setShowDropdown(true); });
  };

  useEffect(() => {
    if (skipSearch.current) { skipSearch.current = false; return; }
    if (!query.trim()) { setResults([]); setShowDropdown(false); return; }
    const timer = setTimeout(() => {
      stockApi.search(query).then((res) => { setResults(res.data); setShowDropdown(true); });
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const fetch5m = (code: string) => {
    if (searchOnly) return;
    setLoading(true);
    setError('');
    stockApi.getCandles5m(code, 1)
      .then((res) => {
        const raw = res.data.data.map((d: any) => ({
          ...d,
          open:  d.open  != null ? Math.round(d.open)  : null,
          high:  d.high  != null ? Math.round(d.high)  : null,
          low:   d.low   != null ? Math.round(d.low)   : null,
          close: d.close != null ? Math.round(d.close) : null,
        }));
        const ma5arr  = calcMA(raw, 5);
        const ma20arr = calcMA(raw, 20);
        const ma60arr = calcMA(raw, 60);
        const closes = raw.map((d: any) => d.close).filter((v: any) => v != null) as number[];
        const rsiArr: (number | null)[] = new Array(raw.length).fill(null);
        if (closes.length >= 15) {
          const win = 14;
          let avgGain = 0; let avgLoss = 0;
          for (let i = 1; i <= win; i++) {
            const diff = closes[i] - closes[i - 1];
            avgGain += Math.max(diff, 0); avgLoss += Math.max(-diff, 0);
          }
          avgGain /= win; avgLoss /= win;
          for (let i = win; i < closes.length; i++) {
            if (i > win) {
              const diff = closes[i] - closes[i - 1];
              avgGain = (avgGain * (win - 1) + Math.max(diff, 0)) / win;
              avgLoss = (avgLoss * (win - 1) + Math.max(-diff, 0)) / win;
            }
            const rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
            rsiArr[i] = Math.round((100 - 100 / (1 + rs)) * 100) / 100;
          }
        }
        const ema = (data: number[], span: number) => {
          const k = 2 / (span + 1);
          return data.reduce<number[]>((acc, v, i) => {
            acc.push(i === 0 ? v : v * k + acc[i - 1] * (1 - k)); return acc;
          }, []);
        };
        const emaFast = ema(closes, 12);
        const emaSlow = ema(closes, 26);
        const macdLine = emaFast.map((f, i) => f - emaSlow[i]);
        const signalLine = ema(macdLine, 9);
        const histLine = macdLine.map((m, i) => m - signalLine[i]);
        const data = raw.map((d: any, i: number) => ({
          ...d,
          ma5: ma5arr[i], ma20: ma20arr[i], ma60: ma60arr[i],
          rsi: rsiArr[i],
          macd: macdLine[i] ?? null,
          macdSignal: signalLine[i] ?? null,
          histogram: histLine[i] ?? null,
        }));
        setChartData(data);
        setViewRange(null);
      })
      .catch(() => setError('5분봉 데이터를 불러오지 못했습니다.'))
      .finally(() => setLoading(false));
  };

  const fetchAll = (code: string, name: string, p: Period) => {
    if (searchOnly) return;
    setLoading(true);
    setError('');
    const displayDays = p === '1m' ? 30 : p === '3m' ? 90 : 180;

    Promise.all([
      stockApi.getCandles(code, 0),
      stockApi.getRSI(code, 'all'),
      stockApi.getMACD(code, 'all'),
      stockApi.getPredictions(undefined, 500, modelId, name),
    ])
      .then(([candleRes, rsiRes, macdRes, predRes]) => {
        const map: Record<string, any> = {};
        candleRes.data.data.forEach((d: any) => {
          const key = d.datetime.slice(0, 10);
          map[key] = {
            ...d, datetime: key,
            open:  d.open  != null ? Math.round(d.open)  : null,
            high:  d.high  != null ? Math.round(d.high)  : null,
            low:   d.low   != null ? Math.round(d.low)   : null,
            close: d.close != null ? Math.round(d.close) : null,
          };
        });
        rsiRes.data.data.forEach((d: any) => {
          if (map[d.date]) map[d.date].rsi = d.rsi;
          else map[d.date] = { datetime: d.date, rsi: d.rsi };
        });
        macdRes.data.data.forEach((d: any) => {
          if (map[d.date]) {
            map[d.date].macd = d.macd;
            map[d.date].macdSignal = d.signal;
            map[d.date].histogram = d.histogram;
          } else {
            map[d.date] = { datetime: d.date, macd: d.macd, macdSignal: d.signal, histogram: d.histogram };
          }
        });
        const sorted = Object.values(map).sort((a, b) => a.datetime.localeCompare(b.datetime));
        const ma5arr = calcMA(sorted, 5);
        const ma20arr = calcMA(sorted, 20);
        const ma60arr = calcMA(sorted, 60);
        const ichimokuRaw = calcIchimoku(sorted);

        // RSI 직접 계산 (DB rsi 필드 없거나 None인 경우 대비)
        const closesForRsi = sorted.map((d: any) => d.close).filter((v: any) => v != null) as number[];
        const rsiCalc: (number | null)[] = new Array(sorted.length).fill(null);
        if (closesForRsi.length >= 15) {
          const win = 14;
          let avgGain = 0; let avgLoss = 0;
          for (let i = 1; i <= win; i++) {
            const diff = closesForRsi[i] - closesForRsi[i - 1];
            avgGain += Math.max(diff, 0); avgLoss += Math.max(-diff, 0);
          }
          avgGain /= win; avgLoss /= win;
          for (let i = win; i < closesForRsi.length; i++) {
            if (i > win) {
              const diff = closesForRsi[i] - closesForRsi[i - 1];
              avgGain = (avgGain * (win - 1) + Math.max(diff, 0)) / win;
              avgLoss = (avgLoss * (win - 1) + Math.max(-diff, 0)) / win;
            }
            const rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
            rsiCalc[i] = Math.round((100 - 100 / (1 + rs)) * 100) / 100;
          }
        }
        const cutDate = new Date();
        cutDate.setDate(cutDate.getDate() - displayDays);
        const cutStr = cutDate.toISOString().slice(0, 10);
        const trimmed = sorted.map((d, i) => {
          const shiftedIdx = i - ICHIMOKU_SHIFT;
          return {
            ...d,
            rsi: d.rsi != null ? d.rsi : rsiCalc[i],
            ma5: ma5arr[i], ma20: ma20arr[i], ma60: ma60arr[i],
            tenkan: ichimokuRaw[i].tenkan,
            kijun:  ichimokuRaw[i].kijun,
            spanA: shiftedIdx >= 0 ? ichimokuRaw[shiftedIdx].spanA : null,
            spanB: shiftedIdx >= 0 ? ichimokuRaw[shiftedIdx].spanB : null,
            cloudTop: shiftedIdx >= 0 && ichimokuRaw[shiftedIdx].spanA != null && ichimokuRaw[shiftedIdx].spanB != null
              ? Math.max(ichimokuRaw[shiftedIdx].spanA!, ichimokuRaw[shiftedIdx].spanB!) : null,
            cloudBottom: shiftedIdx >= 0 && ichimokuRaw[shiftedIdx].spanA != null && ichimokuRaw[shiftedIdx].spanB != null
              ? Math.min(ichimokuRaw[shiftedIdx].spanA!, ichimokuRaw[shiftedIdx].spanB!) : null,
          };
        }).filter((d) => d.datetime >= cutStr);
        const lastDate = trimmed.length ? trimmed[trimmed.length - 1].datetime : '';
        const futureDates: string[] = [];
        const tempD = new Date(lastDate);
        while (futureDates.length < 26) {
          tempD.setDate(tempD.getDate() + 1);
          const day = tempD.getDay();
          if (day !== 0 && day !== 6) futureDates.push(tempD.toISOString().slice(0, 10));
        }
        const futurePadding = futureDates.map((futureDate, i) => {
          const srcIdx = sorted.length - 26 + i;
          const ichi = srcIdx >= 0 ? ichimokuRaw[srcIdx] : null;
          const spanA = ichi?.spanA ?? null;
          const spanB = ichi?.spanB ?? null;
          return {
            datetime: futureDate, spanA, spanB,
            cloudTop: spanA != null && spanB != null ? Math.max(spanA, spanB) : null,
            cloudBottom: spanA != null && spanB != null ? Math.min(spanA, spanB) : null,
          };
        });
        const sigMap: Record<string, string> = {};
        (predRes.data || []).forEach((pd: any) => {
          const date = (pd.predicted_at || '').slice(0, 10);
          sigMap[date] = pd.signal;
        });
        setRawData({ trimmed, futurePadding, sigMap });
        // 마지막 종가 콜백
        const lastClose = trimmed.length ? trimmed[trimmed.length - 1].close : null;
        if (lastClose != null) onPriceUpdate?.(lastClose);
      })
      .catch(() => setError('데이터를 불러오지 못했습니다.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (externalInterval && externalInterval !== chartInterval) {
      setChartInterval(externalInterval);
      if (selected) {
        if (externalInterval === '5m') fetch5m(selected.stock_code);
        else fetchAll(selected.stock_code, selected.stock_name, externalPeriod ?? period);
      }
    }
  }, [externalInterval]);

  const handleIntervalToggle = (interval: ChartInterval) => {
    setChartInterval(interval);
    if (!selected) return;
    if (interval === '5m') fetch5m(selected.stock_code);
    else fetchAll(selected.stock_code, selected.stock_name, externalPeriod ?? period);
  };

  useEffect(() => {
    if (chartInterval !== '5m' || !selected) return;
    const timer = setInterval(() => { fetch5m(selected.stock_code); }, 5 * 60 * 1000);
    return () => clearInterval(timer);
  }, [chartInterval, selected?.stock_code]);

  const handleSelect = (item: StockItem) => {
    skipSearch.current = true;
    setSelected(item); setResults([]); setShowDropdown(false);
    setQuery(item.stock_name);
    onStockChange?.(item.stock_code, item.stock_name);
    if (!searchOnly) {
      if (chartInterval === '5m') fetch5m(item.stock_code);
      else fetchAll(item.stock_code, item.stock_name, externalPeriod ?? period);
    }
  };

  const visData = React.useMemo(
    () => viewRange ? chartData.slice(viewRange[0], viewRange[1] + 1) : chartData,
    [chartData, viewRange]
  );

  const [visPMin, visPMax] = React.useMemo(() => {
    const prices = chartInterval === '5m'
      ? visData.flatMap((d: any) => [d.high, d.low].filter((v: any) => v != null && !isNaN(v)))
      : visData.flatMap((d: any) =>
          [d.high, d.low, d.ma5, d.ma20, d.ma60, d.tenkan, d.kijun, d.spanA, d.spanB].filter((v: any) => v != null && !isNaN(v))
        );
    return prices.length ? [Math.min(...prices) * 0.997, Math.max(...prices) * 1.003] : [0, 100];
  }, [visData, chartInterval]);

  const CandleShape = makeCandleShape(visPMin, visPMax);

  // 현재 보이는 구간(visData) 기준으로 변곡선 계산
  // 가장 최근 극값 1개에서 세트 순서대로 (점점 넓어지는 구조)
  const visInflectionLines = React.useMemo(() => {
    if (!visData.length || chartInterval !== '1d') return [];
    const cycle = inflectionCycle || 26;
    const set = INFLECTION_SETS[cycle] ?? [cycle];
    const closes = visData.map((d: any) => d.close) as (number | null)[];
    const wing = Math.max(3, Math.min(10, Math.floor(visData.length / 10)));

    // 가장 최근 극값 1개만 사용
    let lastPivotIdx = -1;
    for (let i = wing; i < closes.length - wing; i++) {
      const c = closes[i];
      if (c == null) continue;
      const slice = closes.slice(i - wing, i + wing + 1).filter((v) => v != null) as number[];
      if (c === Math.max(...slice) || c === Math.min(...slice)) lastPivotIdx = i;
    }
    if (lastPivotIdx < 0) return [];

    const lines: { date: string; isFuture: boolean }[] = [];
    for (const offset of set) {
      const idx = lastPivotIdx + offset;
      if (idx < visData.length) {
        lines.push({ date: visData[idx].datetime, isFuture: false });
      } else {
        const remaining = idx - (visData.length - 1);
        const d = new Date(visData[visData.length - 1].datetime);
        let added = 0;
        while (added < remaining) {
          d.setDate(d.getDate() + 1);
          if (d.getDay() !== 0 && d.getDay() !== 6) added++;
        }
        lines.push({ date: d.toISOString().slice(0, 10), isFuture: true });
      }
    }
    return lines;
  }, [visData, inflectionCycle, chartInterval]);

  // 변곡 주기 계산 (유저가 선택한 시작/끝 기반)
  const userInflectionLines = React.useMemo(() => {
    if (!inflectionStart || !inflectionEnd || !chartData.length) return [];
    const startIdx = chartData.findIndex((d: any) => d.datetime === inflectionStart);
    const endIdx   = chartData.findIndex((d: any) => d.datetime === inflectionEnd);
    if (startIdx < 0 || endIdx < 0 || startIdx === endIdx) return [];
    const cycle = Math.abs(endIdx - startIdx);
    const baseIdx = Math.min(startIdx, endIdx);

    // 가장 가까운 세트 주기 찾기
    const nearest = INFLECTION_CANDIDATES.reduce((a, b) =>
      Math.abs(a - cycle) <= Math.abs(b - cycle) ? a : b
    );
    const set = INFLECTION_SETS[nearest] ?? [nearest];

    // 시작점(baseIdx)에서 세트 오프셋만큼 앞으로만 변곡선 생성
    // (점점 넓어지는 구조)
    const lines: { date: string; isFuture: boolean }[] = [];
    for (const offset of set) {
      const idx = baseIdx + offset;
      if (idx < chartData.length) {
        lines.push({ date: chartData[idx].datetime, isFuture: false });
      } else {
        const remaining = idx - (chartData.length - 1);
        const d = new Date(chartData[chartData.length - 1].datetime);
        let added = 0;
        while (added < remaining) {
          d.setDate(d.getDate() + 1);
          if (d.getDay() !== 0 && d.getDay() !== 6) added++;
        }
        lines.push({ date: d.toISOString().slice(0, 10), isFuture: true });
      }
    }
    return lines;
  }, [inflectionStart, inflectionEnd, chartData]);

  const activeInflectionLines = (inflectionStart && inflectionEnd) ? userInflectionLines : [];
  const activeCycle = (inflectionStart && inflectionEnd)
    ? Math.abs(
        chartData.findIndex((d: any) => d.datetime === inflectionEnd) -
        chartData.findIndex((d: any) => d.datetime === inflectionStart)
      )
    : 0;

  if (searchOnly) {
    return (
      <div style={{ position: 'relative', display: 'flex', gap: 6 }}>
        <input className="ex-input" value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="종목명 검색" style={{ width: 180 }} />
        <button className="ex-btn" onClick={handleSearch}>검색</button>
        {showDropdown && results.length > 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, zIndex: 999, marginTop: 4,
            background: '#1a1a2e', border: '1px solid #2d2d3d', borderRadius: 8,
            width: 280, maxHeight: 220, overflowY: 'auto', boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
          }}>
            {results.map((r) => (
              <div key={r.stock_code} onClick={() => handleSelect(r)}
                style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 12, color: '#e2e8f0', borderBottom: '1px solid #1e1e2e' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#2d2d3d')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                {r.stock_name}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      {loading && <div className="ex-loading">불러오는 중...</div>}
      {error && <div className="ex-error">{error}</div>}

      {!loading && chartData.length > 0 && chartInterval === '5m' && (
        <div ref={chartWrapRef} onMouseDown={handleMouseDown} onDoubleClick={handleDoubleClick}
          style={{ cursor: 'crosshair', userSelect: 'none' }}>
          <div style={{ fontSize: 10, color: '#666', marginBottom: 2 }}>5분봉 캔들 + MA + MACD + RSI</div>
          <ResponsiveContainer width="100%" height={heights.candle}>
            <ComposedChart data={visData} syncId={SYNC_ID} margin={MARGIN}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis dataKey="datetime" tick={{ fontSize: 9, fill: '#555' }} interval="preserveStartEnd" height={14} />
              <YAxis domain={[visPMin, visPMax]} tick={{ fontSize: 9, fill: '#aaa' }} width={Y_AXIS_WIDTH}
                tickFormatter={(v) => v >= 1000 ? String((v / 1000).toFixed(0)) + 'K' : String(Math.round(v))} />
              <Tooltip content={<CandleTooltip />} />
              <Bar dataKey="close" shape={CandleShape} isAnimationActive={false} maxBarSize={6}>
                {visData.map((d, i) => (
                  <Cell key={i} fill={(d.close ?? 0) >= (d.open ?? 0) ? '#16a34a' : '#dc2626'} />
                ))}
              </Bar>
              <Line type="monotone" dataKey="ma60" stroke="#a78bfa" dot={false} strokeWidth={1.5} connectNulls />
              <Line type="monotone" dataKey="ma20" stroke="#fb923c" dot={false} strokeWidth={1.2} connectNulls />
              <Line type="monotone" dataKey="ma5"  stroke="#facc15" dot={false} strokeWidth={1.2} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
          <div style={{ fontSize: 10, color: '#666', marginTop: 4, marginBottom: 2 }}>MACD</div>
          <ResponsiveContainer width="100%" height={heights.macd}>
            <ComposedChart data={visData} syncId={SYNC_ID} margin={MARGIN}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis dataKey="datetime" tick={false} height={0} />
              <YAxis tick={false} width={Y_AXIS_WIDTH} axisLine={false} tickLine={false} />
              <Tooltip content={<MacdTooltip />} />
              <ReferenceLine y={0} stroke="#555" strokeWidth={1} />
              <Bar dataKey="histogram" isAnimationActive={false} maxBarSize={4}>
                {visData.map((d, i) => (
                  <Cell key={i} fill={(d.histogram ?? 0) >= 0 ? '#16a34a' : '#dc2626'} fillOpacity={0.7} />
                ))}
              </Bar>
              <Line type="monotone" dataKey="macd"       stroke="#6366f1" dot={false} strokeWidth={1.5} connectNulls />
              <Line type="monotone" dataKey="macdSignal" stroke="#f59e0b" dot={false} strokeWidth={1.5} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
          <div style={{ fontSize: 10, color: '#666', marginTop: 4, marginBottom: 2 }}>RSI (14)</div>
          <ResponsiveContainer width="100%" height={heights.rsi}>
            <ComposedChart data={visData} syncId={SYNC_ID} margin={{ ...MARGIN, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis dataKey="datetime" tick={{ fontSize: 9, fill: '#555' }} interval="preserveStartEnd" height={14} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#aaa' }} width={Y_AXIS_WIDTH} ticks={[30, 70]} />
              <Tooltip content={<RsiTooltip />} />
              <ReferenceLine y={70} stroke="#dc2626" strokeDasharray="3 3" strokeOpacity={0.5} />
              <ReferenceLine y={30} stroke="#16a34a" strokeDasharray="3 3" strokeOpacity={0.5} />
              <Line type="monotone" dataKey="rsi" stroke="#6366f1" dot={false} strokeWidth={1.5} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {!loading && chartData.length > 0 && chartInterval === '1d' && (
        <div
          ref={chartWrapRef}
          onMouseDown={inflectionMode ? undefined : handleMouseDown}
          onClick={handleChartClick}
          onDoubleClick={handleDoubleClick}
          style={{ cursor: inflectionMode ? 'crosshair' : 'crosshair', userSelect: 'none' }}
        >
          <div style={{ fontSize: 10, color: '#666', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span>캔들 + 이동평균 + 일목균형표</span>
            {activeCycle > 0 && (
              <span style={{ fontSize: 9, color: '#f59e0b', background: '#f59e0b18', border: '1px solid #f59e0b44', padding: '1px 5px', borderRadius: 3 }}>
                변곡 {activeCycle}봉 주기
              </span>
            )}
            {/* 변곡 설정 버튼 */}
            <div style={{ display: 'flex', gap: 4, marginLeft: 4 }}>
              <button
                onClick={(e) => { e.stopPropagation(); setInflectionMode('start'); setInflectionStart(null); setInflectionEnd(null); }}
                style={{
                  fontSize: 9, padding: '1px 6px', borderRadius: 3, border: '1px solid #f59e0b55', cursor: 'pointer',
                  background: inflectionMode ? '#f59e0b22' : '#1e1e2e',
                  color: inflectionMode ? '#f59e0b' : '#6b7280',
                }}>
                {inflectionMode === 'start' ? '시작점 클릭' : inflectionMode === 'end' ? '끝점 클릭' : '변곡 설정'}
              </button>
              {(inflectionStart || inflectionEnd) && (
                <button
                  onClick={(e) => { e.stopPropagation(); setInflectionStart(null); setInflectionEnd(null); setInflectionMode(null); }}
                  style={{ fontSize: 9, padding: '1px 6px', borderRadius: 3, border: '1px solid #6b728055', cursor: 'pointer', background: '#1e1e2e', color: '#6b7280' }}>
                  초기화
                </button>
              )}
            </div>
            {inflectionStart && !inflectionEnd && (
              <span style={{ fontSize: 9, color: '#f59e0b' }}>시작: {inflectionStart} → 끝점을 클릭하세요</span>
            )}
          </div>
          <ResponsiveContainer width="100%" height={heights.candle}>
            <ComposedChart data={visData} syncId={SYNC_ID} margin={MARGIN}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis dataKey="datetime" tick={{ fontSize: 9, fill: '#555' }} interval="preserveStartEnd" height={14} />
              <YAxis domain={[visPMin, visPMax]} tick={{ fontSize: 9, fill: '#aaa' }} width={Y_AXIS_WIDTH}
                tickFormatter={(v) => v >= 1000000 ? String((v/1000000).toFixed(1)) + 'M' : v >= 1000 ? String((v/1000).toFixed(0)) + 'K' : String(Math.round(v))} />
              <Tooltip content={<CandleTooltip />} />
              <Legend verticalAlign="top" wrapperStyle={{ fontSize: 10, paddingBottom: 2 }}
                content={() => (
                  <div style={{ display: 'flex', gap: 12, paddingBottom: 4, fontSize: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                    {[
                      { name: 'MA5', color: '#facc15' }, { name: 'MA20', color: '#fb923c' }, { name: 'MA60', color: '#a78bfa' },
                      { name: '전환선', color: '#38bdf8' }, { name: '기준선', color: '#f472b6' },
                      { name: '선행A', color: '#4ade80' }, { name: '선행B', color: '#f87171' },
                    ].map((m) => (
                      <span key={m.name} style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#aaa' }}>
                        <span style={{ width: 16, height: 2, background: m.color, display: 'inline-block' }} />
                        {m.name}
                      </span>
                    ))}
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#f59e0b', fontSize: 9 }}>
                      <span style={{ width: 1, height: 10, background: '#f59e0b', display: 'inline-block' }} />
                      변곡
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#f59e0b88', fontSize: 9 }}>
                      <span style={{ width: 1, height: 10, background: '#f59e0b', display: 'inline-block', opacity: 0.4 }} />
                      변곡(예정)
                    </span>
                    <span style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
                      <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: '#16a34a', color: '#fff' }}>BUY (AI)</span>
                      <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: '#dc2626', color: '#fff' }}>SELL (AI)</span>
                      <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: '#7e22ce', color: '#f0abfc' }}>골든보</span>
                      {sellMode === 'simple' && (
                        <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: '#78350f55', color: '#d97706', border: '1px solid #d97706' }}>SELL (단순)</span>
                      )}
                    </span>
                  </div>
                )} />
              {/* 변곡선 - 활성 소스 기준 */}
              {activeInflectionLines.filter(l => {
                const first = visData[0]?.datetime;
                const last = visData[visData.length - 1]?.datetime;
                return l.date >= first && l.date <= last;
              }).map((l, i) => (
                <ReferenceLine key={`inf-${i}`} x={l.date}
                  stroke={l.isFuture ? '#f59e0b44' : '#f59e0b'}
                  strokeWidth={l.isFuture ? 1 : 1.2}
                  strokeDasharray={l.isFuture ? '4 3' : '3 2'}
                  label={l.isFuture ? { value: '?', position: 'top', fill: '#f59e0b44', fontSize: 8 } : undefined}
                />
              ))}
              {/* 선택 중인 시작점 표시 */}
              {inflectionStart && (
                <ReferenceLine x={inflectionStart} stroke="#34d399" strokeWidth={1.5} strokeDasharray="4 2"
                  label={{ value: 'S', position: 'top', fill: '#34d399', fontSize: 9 }} />
              )}
              {inflectionEnd && (
                <ReferenceLine x={inflectionEnd} stroke="#f472b6" strokeWidth={1.5} strokeDasharray="4 2"
                  label={{ value: 'E', position: 'top', fill: '#f472b6', fontSize: 9 }} />
              )}
              <Bar dataKey="close" shape={CandleShape} isAnimationActive={false} maxBarSize={20} name="캔들" legendType="none">
                {visData.map((d, i) => (
                  <Cell key={i}
                    fill={(d.close ?? 0) >= (d.open ?? 0) ? '#16a34a' : '#dc2626'}
                    fillOpacity={d.ichimokuStagnant ? 0.15 : d.ma60Falling ? 0.25 : 1}
                  />
                ))}
              </Bar>
              <Line type="monotone" dataKey="ma60"   stroke="#a78bfa" dot={false} strokeWidth={1.5} connectNulls legendType="none" />
              <Line type="monotone" dataKey="ma20"   stroke="#fb923c" dot={false} strokeWidth={1.2} connectNulls legendType="none" />
              <Line type="monotone" dataKey="ma5"    stroke="#facc15" dot={false} strokeWidth={1.2} connectNulls legendType="none" />
              <Line type="monotone" dataKey="tenkan" stroke="#38bdf8" dot={false} strokeWidth={1.2} connectNulls legendType="none" />
              <Line type="monotone" dataKey="kijun"  stroke="#f472b6" dot={false} strokeWidth={1.2} connectNulls legendType="none" />
              <Area type="monotone" dataKey="cloudTop"    stroke="none" fill="#4ade80" fillOpacity={0.12} connectNulls legendType="none" baseValue="dataMin" />
              <Area type="monotone" dataKey="cloudBottom" stroke="none" fill="#0a0a14" fillOpacity={1}    connectNulls legendType="none" baseValue="dataMin" />
              <Line type="monotone" dataKey="spanA"  stroke="#4ade80" dot={false} strokeWidth={0.8} connectNulls legendType="none" strokeDasharray="3 2" />
              <Line type="monotone" dataKey="spanB"  stroke="#f87171" dot={false} strokeWidth={0.8} connectNulls legendType="none" strokeDasharray="3 2" />
            </ComposedChart>
          </ResponsiveContainer>

          <div style={{ fontSize: 10, color: '#666', marginTop: 4, marginBottom: 2, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span>MACD</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#aaa', fontSize: 9 }}><span style={{ width: 14, height: 2, background: '#6366f1', display: 'inline-block' }} />MACD</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#aaa', fontSize: 9 }}><span style={{ width: 14, height: 2, background: '#f59e0b', display: 'inline-block' }} />시그널</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#aaa', fontSize: 9 }}><span style={{ width: 8, height: 8, background: '#16a34a', display: 'inline-block', borderRadius: 1 }} />양/음봉</span>
          </div>
          <ResponsiveContainer width="100%" height={heights.macd}>
            <ComposedChart data={visData} syncId={SYNC_ID} margin={MARGIN}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis dataKey="datetime" tick={false} height={0} />
              <YAxis tick={false} width={Y_AXIS_WIDTH} axisLine={false} tickLine={false} />
              <Tooltip content={<MacdTooltip />} />
              <ReferenceLine y={0} stroke="#555" strokeWidth={1} label={{ value: '0', position: 'left', fill: '#555', fontSize: 9 }} />
              {activeInflectionLines.filter(l => {
                const first = visData[0]?.datetime;
                const last = visData[visData.length - 1]?.datetime;
                return l.date >= first && l.date <= last;
              }).map((l, i) => (
                <ReferenceLine key={`inf-m-${i}`} x={l.date} stroke={l.isFuture ? '#f59e0b33' : '#f59e0b66'} strokeWidth={1} strokeDasharray="3 2" />
              ))}
              <Bar dataKey="histogram" isAnimationActive={false} maxBarSize={8}>
                {visData.map((d, i) => (
                  <Cell key={i} fill={(d.histogram ?? 0) >= 0 ? '#16a34a' : '#dc2626'} fillOpacity={0.7} />
                ))}
              </Bar>
              <Line type="monotone" dataKey="macd"       stroke="#6366f1" dot={false} strokeWidth={1.5} connectNulls />
              <Line type="monotone" dataKey="macdSignal" stroke="#f59e0b" dot={false} strokeWidth={1.5} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>

          <div style={{ fontSize: 10, color: '#666', marginTop: 4, marginBottom: 2, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span>RSI (14)</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#aaa', fontSize: 9 }}><span style={{ width: 14, height: 2, background: '#6366f1', display: 'inline-block' }} />RSI</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#dc2626', fontSize: 9 }}>— 70 과매수</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#16a34a', fontSize: 9 }}>— 30 과매도</span>
          </div>
          <ResponsiveContainer width="100%" height={heights.rsi}>
            <ComposedChart data={visData} syncId={SYNC_ID} margin={{ ...MARGIN, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis dataKey="datetime" tick={{ fontSize: 9, fill: '#555' }} interval="preserveStartEnd" height={14} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#aaa' }} width={Y_AXIS_WIDTH} ticks={[30, 70]} />
              <Tooltip content={<RsiTooltip />} />
              <ReferenceLine y={70} stroke="#dc2626" strokeDasharray="3 3" strokeOpacity={0.5} />
              <ReferenceLine y={30} stroke="#16a34a" strokeDasharray="3 3" strokeOpacity={0.5} />
              {activeInflectionLines.filter(l => {
                const first = visData[0]?.datetime;
                const last = visData[visData.length - 1]?.datetime;
                return l.date >= first && l.date <= last;
              }).map((l, i) => (
                <ReferenceLine key={`inf-r-${i}`} x={l.date} stroke={l.isFuture ? '#f59e0b33' : '#f59e0b66'} strokeWidth={1} strokeDasharray="3 2" />
              ))}
              <Line type="monotone" dataKey="rsi" stroke="#6366f1" dot={false} strokeWidth={1.5} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};

export default StockSearchSection;
