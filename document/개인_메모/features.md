# 피처 목록 (차트 분석 기반 파생변수)

## 이동평균선 계열

| 피처명 | 설명 |
|---|---|
| ma5 | 5일 이동평균선 |
| ma10 | 10일 이동평균선 |
| ma20 | 20일 이동평균선 |
| ma60 | 60일 이동평균선 |
| ma120 | 120일 이동평균선 |
| ma240 | 240일 이동평균선 |
| is_uptrend | 정배열 여부 (ma5 > ma10 > ma20 > ma60 순서) |
| is_downtrend | 역배열 여부 |
| ma_spread_5_60 | 5일선과 60일선 간격 - 좁을수록 강한 상승 |
| ma_spread_10_60 | 10일선과 60일선 간격 |
| ma60_gap | 60일선 괴리율 (close - ma60) / ma60 |
| ma10_break | 10일선 종가 이탈 여부 - 매도 시그널 |
| ma_cross_5_10 | 5일선이 10일선 상향 돌파 여부 - 골든크로스 |
| ma_cross_5_10_dead | 5일선이 10일선 하향 이탈 여부 - 데드크로스 |
| candle_above_ma60 | 캔들이 60일선 위에 있는지 여부 |

---

## RSI 계열

| 피처명 | 설명 |
|---|---|
| rsi_9 | RSI 9일 |
| rsi_above_70 | RSI 70 초과 여부 - 과열 |
| rsi_exit_70 | RSI 70 상향 후 하방 이탈 여부 - 매도 시그널 |
| rsi_above_50 | RSI 50 초과 여부 - 매수 우호적 |
| rsi_ma | RSI 이동평균선 |
| rsi_touch_ma_count | RSI가 이동평균선을 터치한 횟수 - 2회 시 상승 패턴 |

---

## MACD 계열

| 피처명 | 설명 |
|---|---|
| macd | MACD 선 (12일 - 25일 지수이평) |
| macd_signal | 시그널 선 (60일 이평) |
| macd_hist | 히스토그램 |
| macd_uptrend | MACD 정배열 여부 |
| macd_above_zero | MACD가 0선 위에 있는지 여부 |
| macd_near_zero | MACD가 0선 근처로 수렴 여부 - 매수 진입 타이밍 |

---

## 볼린저밴드 계열

| 피처명 | 설명 |
|---|---|
| bb_upper | 상단밴드 |
| bb_mid | 중간선 (20일 이평) |
| bb_lower | 하단밴드 |
| bb_pct | 밴드 내 위치 (0=하단, 1=상단) |
| bb_upper_break | 상단 이탈 여부 - 매도 시그널 |
| bb_lower_support | 하단 지지 여부 - 매수 검토 |
| bb_width | 밴드 폭 - 변동성 크기 |

---

## 일목균형표 계열

| 피처명 | 설명 |
|---|---|
| ichi_conversion | 전환선 (9일 고저 평균) |
| ichi_base | 기준선 (26일 고저 평균) |
| ichi_span_a | 선행스팬A (전환선 + 기준선) / 2 |
| ichi_span_b | 선행스팬B (52일 고저 평균) |
| ichi_above_cloud | 캔들이 구름 위에 있는지 여부 |
| ichi_below_cloud | 캔들이 구름 아래에 있는지 여부 |
| ichi_in_cloud | 캔들이 구름 안에 있는지 여부 - 훼이크 구간 |
| ichi_conversion_cross | 전환선이 기준선 상향 돌파 여부 |
| cloud_green | 구름이 양운(초록)인지 여부 |
| cloud_thickness | 구름 두께 - 두꺼울수록 강한 지지저항 |

---

## 피보나치 계열

| 피처명 | 설명 |
|---|---|
| fib_786_support | 78.6% 피보나치 지지 여부 |
| fib_618_level | 61.8% 구간 위치 여부 |
| fib_500_level | 50% 구간 위치 여부 |
| prev_high_break | 전고점 돌파 여부 - 추가 상승 신호 |
| prev_high_fail | 전고점 돌파 실패 여부 - 훼이크 신호 |

---

## 추세 및 지지저항 계열

| 피처명 | 설명 |
|---|---|
| higher_high | 현재 고점이 이전 고점보다 높은지 여부 |
| higher_low | 현재 저점이 이전 저점보다 높은지 여부 - 쌍바닥 패턴 |
| lower_high | 현재 고점이 이전 고점보다 낮은지 여부 - 하락 추세 |
| support_break | 지지선 이탈 여부 |
| resistance_break | 저항선 돌파 여부 - 매수 시그널 |
| trendline_touch_count | 추세선 터치 횟수 - 3회째 돌파 시 강한 신호 |
| double_bottom | 쌍바닥 패턴 여부 |
| right_bottom_higher | 쌍바닥에서 오른쪽 저점이 왼쪽보다 높은지 여부 |

---

## 캔들 패턴 계열

| 피처명 | 설명 |
|---|---|
| body_ratio | 캔들 몸통 비율 abs(close - open) / (high - low) |
| is_bullish | 양봉 여부 |
| is_bearish | 음봉 여부 |
| is_doji | 도지 캔들 여부 - 몸통 거의 없음 |
| gap_up | 갭 상승 여부 (전일 종가 < 당일 시가) |
| gap_down | 갭 하락 여부 |
| gap_fill_rate | 갭 매꿈 진행률 |
| upper_wick_ratio | 위꼬리 비율 |
| lower_wick_ratio | 아래꼬리 비율 |

---

## 거래량 계열

| 피처명 | 설명 |
|---|---|
| vol_ratio_20 | 거래량 / 20일 평균 거래량 - 급등 비율 |
| vol_up_with_price_up | 거래량 증가 + 주가 상승 동반 여부 |
| vol_down_with_price_up | 거래량 감소 + 주가 상승 - 추세 약화 신호 |
| vol_spike | 거래량 급등 여부 (2배 이상) |

---

## 시장 지표 계열

| 피처명 | 설명 |
|---|---|
| kospi_trend | 코스피 추세 방향 |
| nasdaq_trend | 나스닥 추세 방향 |
| usd_krw_change | 달러/원 환율 변화율 - 하락 시 코스피 우호 |
| vix_level | VIX 공포지수 - 높을수록 시장 불안 |
| foreign_net_buy | 외국인 순매수 여부 |
| institution_net_buy | 기관 순매수 여부 |
| individual_net_buy | 개인 순매수 여부 |
