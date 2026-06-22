import React, { useState } from 'react';
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Bar, Cell, Legend,
} from 'recharts';
import { stockApi, StockItem } from '../../api/stock';

type Period = '1m' | '3m' | '6m';

const Y_AXIS_WIDTH = 65;
const SYNC_ID = 'stock-sync';
const MARGIN = { left: 0, right: 16, top: 8, bottom: 0 };

// ── 이동평균 계산 ─────────────────────────────────────────────────────────────
const calcMA = (data: any[], n: number): (number | null)[] =>
  data.map((_, i) => {
    if (i < n - 1) return null;
    const slice = data.slice(i - n + 1, i + 1);
    const vals = slice.map((d) => d.close).filter((v) => v != null);
    if (vals.length < n) return null;
    return Math.round(vals.reduce((s, v) => s + v, 0) / n);
  });

// ── 일목균형표 계산 ───────────────────────────────────────────────────────────
const calcIchimoku = (data: any[]) => {
  const hi = (i: number, n: number) =>
    Math.max(...data.slice(Math.max(0, i - n + 1), i + 1).map((d) => d.high ?? -Infinity));
  const lo = (i: number, n: number) =>
    Math.min(...data.slice(Math.max(0, i - n + 1), i + 1).map((d) => d.low ?? Infinity));

  return data.map((_, i) => {
    const tenkan = i >= 8 ? Math.round((hi(i, 9) + lo(i, 9)) / 2) : null;
    const kijun = i >= 25 ? Math.round((hi(i, 26) + lo(i, 26)) / 2) : null;
    const spanA = tenkan != null && kijun != null ? Math.round((tenkan + kijun) / 2) : null;
    const spanB = i >= 51 ? Math.round((hi(i, 52) + lo(i, 52)) / 2) : null;
    return { tenkan, kijun, spanA, spanB };
  });
};

// ── 캔들 shape ────────────────────────────────────────────────────────────────
const makeCandleShape = (domainMin: number, domainMax: number) => (props: any) => {
  const { x, y, width, height, payload } = props;
  if (!payload || payload.open == null || payload.close == null) return null;
  if (y == null || height == null || !width || height === 0) return null;

  const { open, high, low, close } = payload;
  const isUp = close >= open;
  const color = isUp ? '#16a34a' : '#dc2626';

  const domainMinPixel = y + height;
  const pixelPerUnit = height / (close - domainMin);
  const toY = (v: number) => domainMinPixel - (v - domainMin) * pixelPerUnit;

  const openY = toY(open);
  const closeY = toY(close);
  const highY = toY(high ?? Math.max(open, close));
  const lowY = toY(low ?? Math.min(open, close));
  const bodyTop = Math.min(openY, closeY);
  const bodyH = Math.max(Math.abs(openY - closeY), 1);
  const bw = Math.max(width - 2, 2);
  const cx = x + width / 2;

  return (
    <g>
      <line x1={cx} y1={highY} x2={cx} y2={bodyTop} stroke={color} strokeWidth={1.5} />
      <line x1={cx} y1={bodyTop + bodyH} x2={cx} y2={lowY} stroke={color} strokeWidth={1.5} />
      {/* 양봉/음봉 모두 채움 */}
      <rect x={cx - bw / 2} y={bodyTop} width={bw} height={bodyH}
        fill={color} stroke={color} strokeWidth={1} />
    </g>
  );
};

// ── 툴팁 ──────────────────────────────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  const fmt = (v: any) => v != null ? Math.round(v).toLocaleString() : '-';
  const row = (lbl: string, val: any, color = '#fff') => (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 20 }}>
      <span style={{ color: '#888' }}>{lbl}</span>
      <span style={{ color, fontWeight: 500 }}>{val}</span>
    </div>
  );
  return (
    <div style={{
      background: '#12121f', border: '1px solid #2d2d3d',
      borderRadius: 6, padding: '10px 14px', fontSize: 12, minWidth: 190,
    }}>
      <div style={{ color: '#6366f1', marginBottom: 6, fontWeight: 600 }}>{label}</div>
      {d.open != null && <>
        {row('시가', fmt(d.open))} {row('고가', fmt(d.high), '#16a34a')}
        {row('저가', fmt(d.low), '#dc2626')} {row('종가', fmt(d.close))}
      </>}
      {d.ma5 != null && <div style={{ marginTop: 4 }}>
        {row('MA5', fmt(d.ma5), '#facc15')}
        {row('MA20', fmt(d.ma20), '#fb923c')}
        {row('MA60', fmt(d.ma60), '#a78bfa')}
      </div>}
      {d.tenkan != null && <div style={{ marginTop: 4 }}>
        {row('전환선', fmt(d.tenkan), '#38bdf8')}
        {row('기준선', fmt(d.kijun), '#f472b6')}
        {d.spanA != null && row('선행A', fmt(d.spanA), '#4ade80')}
        {d.spanB != null && row('선행B', fmt(d.spanB), '#f87171')}
      </div>}
      {d.rsi != null && <div style={{ marginTop: 4 }}>{row('RSI', d.rsi, '#6366f1')}</div>}
      {d.macd != null && <div style={{ marginTop: 4 }}>
        {row('MACD', Math.round(d.macd).toLocaleString(), '#6366f1')}
        {row('시그널', Math.round(d.macdSignal ?? 0).toLocaleString(), '#f59e0b')}
      </div>}
    </div>
  );
};

const StockSearchSection: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StockItem[]>([]);
  const [selected, setSelected] = useState<StockItem | null>(null);
  const [period, setPeriod] = useState<Period>('3m');
  const [chartData, setChartData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);

  const handleSearch = () => {
    if (!query.trim()) return;
    stockApi.search(query).then((res) => { setResults(res.data); setShowDropdown(true); });
  };

  const fetchAll = (code: string, p: Period) => {
    setLoading(true);
    setError('');
    const dayCount = p === '1m' ? 30 : p === '3m' ? 90 : 180;
    Promise.all([
      stockApi.getCandles(code, dayCount),
      stockApi.getRSI(code, p),
      stockApi.getMACD(code, p),
    ])
      .then(([candleRes, rsiRes, macdRes]) => {
        const map: Record<string, any> = {};
        candleRes.data.data.forEach((d: any) => {
          const key = d.datetime.slice(0, 10);
          map[key] = {
            ...d, datetime: key,
            open: d.open != null ? Math.round(d.open) : null,
            high: d.high != null ? Math.round(d.high) : null,
            low: d.low != null ? Math.round(d.low) : null,
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

        // 이동평균 계산 (close 기반)
        const ma5arr = calcMA(sorted, 5);
        const ma20arr = calcMA(sorted, 20);
        const ma60arr = calcMA(sorted, 60);

        // 일목균형표 계산 (high/low 기반)
        const ichimoku = calcIchimoku(sorted);

        const final = sorted.map((d, i) => ({
          ...d,
          ma5: ma5arr[i],
          ma20: ma20arr[i],
          ma60: ma60arr[i],
          tenkan: ichimoku[i].tenkan,
          kijun: ichimoku[i].kijun,
          spanA: ichimoku[i].spanA,
          spanB: ichimoku[i].spanB,
        }));

        setChartData(final);
      })
      .catch(() => setError('데이터를 불러오지 못했습니다.'))
      .finally(() => setLoading(false));
  };

  const handleSelect = (item: StockItem) => {
    setSelected(item); setResults([]); setShowDropdown(false);
    setQuery(item.stock_name); fetchAll(item.stock_code, period);
  };

  const prices = chartData.flatMap((d) =>
    [d.high, d.low, d.ma5, d.ma20, d.ma60, d.tenkan, d.kijun, d.spanA, d.spanB]
      .filter((v) => v != null && !isNaN(v))
  );
  const pMin = prices.length ? Math.min(...prices) * 0.997 : 0;
  const pMax = prices.length ? Math.max(...prices) * 1.003 : 100;

  const CandleShape = makeCandleShape(pMin, pMax);

  return (
    <div>
      <div style={{ position: 'relative', display: 'inline-block', marginBottom: 16 }}>
        <div className="ex-search-row" style={{ marginBottom: 0 }}>
          <input className="ex-input" value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="종목명 또는 종목코드 입력" />
          <button className="ex-btn" onClick={handleSearch}>검색</button>
        </div>
        {showDropdown && results.length > 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, zIndex: 999,
            background: '#1a1a2e', border: '1px solid #2d2d3d', borderRadius: 8,
            width: 300, maxHeight: 220, overflowY: 'auto', boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
          }}>
            {results.map((r) => (
              <div key={r.stock_code} onClick={() => handleSelect(r)}
                style={{ padding: '10px 14px', cursor: 'pointer', fontSize: 13, color: '#e2e8f0', borderBottom: '1px solid #2d2d3d' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#2d2d3d')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                {r.stock_name} ({r.stock_code})
              </div>
            ))}
          </div>
        )}
      </div>

      {selected && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <h3 className="ex-stock-title" style={{ margin: 0 }}>{selected.stock_name}</h3>
            {(['1m', '3m', '6m'] as Period[]).map((p) => (
              <button key={p} className={`ex-filter-btn${period === p ? ' active' : ''}`}
                onClick={() => { setPeriod(p); fetchAll(selected.stock_code, p); }}>{p}</button>
            ))}
          </div>

          {loading && <div className="ex-loading">불러오는 중...</div>}
          {error && <div className="ex-error">{error}</div>}

          {!loading && chartData.length > 0 && (
            <>
              <div style={{ fontSize: 11, color: '#888', marginBottom: 4 }}>캔들 + 이동평균 + 일목균형표</div>
              <ResponsiveContainer width="100%" height={340}>
                <ComposedChart data={chartData} syncId={SYNC_ID} margin={MARGIN}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis dataKey="datetime" tick={{ fontSize: 10, fill: '#555' }} interval="preserveStartEnd" />
                  <YAxis
                    domain={[pMin, pMax]} tick={{ fontSize: 10, fill: '#aaa' }} width={Y_AXIS_WIDTH}
                    tickFormatter={(v) =>
                      v >= 1000000 ? `${(v / 1000000).toFixed(1)}M`
                      : v >= 1000 ? `${(v / 1000).toFixed(0)}K`
                      : String(Math.round(v))
                    }
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11, paddingBottom: 4 }}
                    formatter={(value) => <span style={{ color: '#aaa' }}>{value}</span>} />

                  {/* 캔들 */}
                  <Bar dataKey="close" shape={CandleShape} isAnimationActive={false} maxBarSize={20} name="캔들" legendType="none">
                    {chartData.map((d, i) => (
                      <Cell key={i} fill={(d.close ?? 0) >= (d.open ?? 0) ? '#16a34a' : '#dc2626'} />
                    ))}
                  </Bar>

                  {/* 이동평균선 */}
                  <Line type="monotone" dataKey="ma5" stroke="#facc15" dot={false} strokeWidth={1.2} connectNulls name="MA5" />
                  <Line type="monotone" dataKey="ma20" stroke="#fb923c" dot={false} strokeWidth={1.2} connectNulls name="MA20" />
                  <Line type="monotone" dataKey="ma60" stroke="#a78bfa" dot={false} strokeWidth={1.5} connectNulls name="MA60" />

                  {/* 일목균형표 */}
                  <Line type="monotone" dataKey="tenkan" stroke="#38bdf8" dot={false} strokeWidth={1} connectNulls name="전환선" strokeDasharray="4 2" />
                  <Line type="monotone" dataKey="kijun" stroke="#f472b6" dot={false} strokeWidth={1} connectNulls name="기준선" strokeDasharray="4 2" />
                  <Line type="monotone" dataKey="spanA" stroke="#4ade80" dot={false} strokeWidth={1} connectNulls name="선행A" strokeDasharray="2 2" />
                  <Line type="monotone" dataKey="spanB" stroke="#f87171" dot={false} strokeWidth={1} connectNulls name="선행B" strokeDasharray="2 2" />
                </ComposedChart>
              </ResponsiveContainer>

              <div style={{ fontSize: 11, color: '#888', marginTop: 8, marginBottom: 4 }}>RSI (14)</div>
              <ResponsiveContainer width="100%" height={110}>
                <ComposedChart data={chartData} syncId={SYNC_ID} margin={MARGIN}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis dataKey="datetime" tick={false} height={0} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#aaa' }} width={Y_AXIS_WIDTH} ticks={[0, 30, 70, 100]} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={70} stroke="#dc2626" strokeDasharray="3 3" strokeOpacity={0.5} />
                  <ReferenceLine y={30} stroke="#16a34a" strokeDasharray="3 3" strokeOpacity={0.5} />
                  <Line type="monotone" dataKey="rsi" stroke="#6366f1" dot={false} strokeWidth={1.5} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>

              <div style={{ fontSize: 11, color: '#888', marginTop: 8, marginBottom: 4 }}>MACD</div>
              <ResponsiveContainer width="100%" height={120}>
                <ComposedChart data={chartData} syncId={SYNC_ID} margin={{ ...MARGIN, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis dataKey="datetime" tick={{ fontSize: 10, fill: '#555' }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10, fill: '#aaa' }} width={Y_AXIS_WIDTH} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={0} stroke="#444" />
                  <Bar dataKey="histogram" isAnimationActive={false} maxBarSize={8}>
                    {chartData.map((d, i) => (
                      <Cell key={i} fill={(d.histogram ?? 0) >= 0 ? '#16a34a' : '#dc2626'} fillOpacity={0.7} />
                    ))}
                  </Bar>
                  <Line type="monotone" dataKey="macd" stroke="#6366f1" dot={false} strokeWidth={1.5} connectNulls />
                  <Line type="monotone" dataKey="macdSignal" stroke="#f59e0b" dot={false} strokeWidth={1.5} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            </>
          )}
        </>
      )}
    </div>
  );
};

export default StockSearchSection;
