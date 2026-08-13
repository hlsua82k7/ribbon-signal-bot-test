"""
資料來源抽象層：
- crypto  -> ccxt (Binance 現貨)
- us_stocks / forex -> yfinance

統一回傳格式: DataFrame，index 是時間(tz-aware)，欄位小寫 open/high/low/close/volume。
"""

import pandas as pd
import ccxt
import yfinance as yf

# yfinance 沒有原生 4h，用 1h resample 出來
YF_NATIVE_INTERVAL = {
    "15m": ("15m", "60d"),
    "1h": ("60m", "180d"),
    "1d": ("1d", "5y"),
    "1w": ("1wk", "10y"),
}


def _normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    return df[["open", "high", "low", "close", "volume"]].dropna()


def _resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {
        "open": df["open"].resample(rule).first(),
        "high": df["high"].resample(rule).max(),
        "low": df["low"].resample(rule).min(),
        "close": df["close"].resample(rule).last(),
        "volume": df["volume"].resample(rule).sum(),
    }
    out = pd.concat(agg, axis=1)
    return out.dropna()


def fetch_crypto(symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
    ex = ccxt.binance()
    ex.enableRateLimit = True
    raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("dt", inplace=True)
    return df[["open", "high", "low", "close", "volume"]]


def fetch_yf(symbol: str, timeframe: str) -> pd.DataFrame:
    if timeframe == "4h":
        interval, period = YF_NATIVE_INTERVAL["1h"]
        raw = yf.download(symbol, interval=interval, period=period,
                           progress=False, auto_adjust=False)
        base = _normalize_yf(raw)
        return _resample_ohlc(base, "4h")

    if timeframe not in YF_NATIVE_INTERVAL:
        raise ValueError(f"不支援的 yfinance 週期: {timeframe}")

    interval, period = YF_NATIVE_INTERVAL[timeframe]
    raw = yf.download(symbol, interval=interval, period=period,
                       progress=False, auto_adjust=False)
    return _normalize_yf(raw)


def fetch(market: str, symbol: str, timeframe: str) -> pd.DataFrame:
    if market == "crypto":
        return fetch_crypto(symbol, timeframe)
    return fetch_yf(symbol, timeframe)
