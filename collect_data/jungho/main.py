import pandas as pd
import yfinance as yf

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

    # 🔥 영선 (0 기준선)
    zero_line = pd.DataFrame(0, index=macd.index, columns=macd.columns)

    return macd, signal, zero_line

# 1. 엑셀 읽기
df = pd.read_excel("kospi_list.xlsx")

# 2. 종목코드 처리
df['종목코드'] = df['종목코드'].astype(str).str.zfill(6)

# 3. 티커 생성
tickers = df['종목코드'].apply(lambda x: x + ".KS").tolist()

print("티커 샘플:", tickers[:10])

# 4. 데이터 가져오기 (테스트용 5개)
data = yf.download(tickers[:5], start="2022-01-01")

# 🔥 핵심: 종가 데이터 추출
close = data['Close']

# 5. RSI / MACD 계산
rsi = calculate_rsi(close)
macd, signal, zero_line = calculate_macd(close)

# 6. 매수 / 매도 신호
buy_signal = (rsi < 30) & (macd > signal)
sell_signal = (rsi > 70) | (macd < signal)
neutral_signal = (rsi < 50) | (macd < zero_line & macd < signal & signal < zero_line)

# 7. 결과 확인 (한 종목 예시)
ticker = tickers[0]

print(f"\n=== {ticker} 매수 신호 ===")
print(buy_signal[ticker][buy_signal[ticker] == True].tail())

print(f"\n=== {ticker} 관망 신호 ===")
print(neutral_signal[ticker][neutral_signal[ticker] == True].tail())

print(f"\n=== {ticker} 매도 신호 ===")
print(sell_signal[ticker][sell_signal[ticker] == True].tail())