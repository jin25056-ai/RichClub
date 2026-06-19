import pandas as pd
import yfinance as yf
import re

# RSI 계산
def calculate_rsi(df, period=14):
    delta = df.diff()

    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi

# MACD 계산
def calculate_macd(df):
    ema12 = df.ewm(span=12).mean()
    ema26 = df.ewm(span=26).mean()

    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()

    zero_line = pd.DataFrame(0, index=macd.index, columns=macd.columns)

    return macd, signal, zero_line


# 1. 엑셀 읽기
df = pd.read_excel("kospi_list.xlsx")

# 2. 종목코드 처리
df['종목코드'] = df['종목코드'].astype(str).str.zfill(6)

# 3. 티커 생성
df['티커'] = df['종목코드'].apply(lambda x: x + ".KS")
tickers = df['티커'].tolist()

# 🔥 종목명 매핑
ticker_to_name = dict(zip(df['티커'], df['종목명']))

print("티커 샘플:", tickers[:10])

# 4. 데이터 가져오기
data = yf.download(tickers, start="2022-01-01")

# OHLCV 분리
open_ = data['Open']
high = data['High']
low = data['Low']
close = data['Close']
volume = data['Volume']

# 5. RSI / MACD 계산
rsi = calculate_rsi(close)
macd, signal, zero_line = calculate_macd(close)

# 6. 매수 / 매도 / 관망 신호
buy_signal = (rsi < 30) & (macd > signal)
sell_signal = (rsi > 70) | (macd < signal)
neutral_signal = (rsi < 50) | ((macd < zero_line) & (macd < signal) & (signal < zero_line))

# 7. 전체 종목 파일로 저장
for ticker in tickers:

    try:
        name = ticker_to_name.get(ticker, ticker)
        safe_name = re.sub(r'[\\/:*?"<>|]', '', name)

        result = pd.DataFrame(index=close.index)

        # OHLCV (주가)
        result["open"] = open_[ticker]
        result["high"] = high[ticker]
        result["low"] = low[ticker]
        result["close"] = close[ticker]
        result["volume"] = volume[ticker]

        # 지표
        result["rsi"] = rsi[ticker]
        result["macd"] = macd[ticker]
        result["signal"] = signal[ticker]

        # 액션
        signal_label = pd.Series(index=close.index, dtype="object")

        signal_label[buy_signal[ticker]] = "매수"
        signal_label[neutral_signal[ticker]] = "관망"
        signal_label[sell_signal[ticker]] = "매도"

        result["action"] = signal_label

        # NaN 제거
        result = result.dropna()

        # 저장
        result.to_csv(f"./company_signals/{safe_name}.csv", encoding="utf-8-sig")

        print(f"{safe_name} 저장 완료")

    except Exception as e:
        print(f"{ticker} 실패: {e}")