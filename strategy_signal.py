# strategy_signal.py
"""
Strategy:
- Detect market trend using 1D, 4H, 1H by price slope + volume confirmation.
- Detect EMA7 x EMA99 crossover on M15.
- If crossover direction aligns with market trend -> produce LONG/SHORT signal.
- TP = 2% from entry price.

This module DOES NOT place orders automatically. It returns a signal dict that you can pass to
your order module (order_client.place_order).
"""

from binance.client import Client
from dotenv import load_dotenv
import os
import pandas as pd
import numpy as np
from scipy.stats import linregress
import math
from datetime import timezone, timedelta
from load_env import *
import talib

# ---------- Helpers ----------
def fetch_klines(symbol: str, interval: str, limit: int = 200):
    """
    Return DataFrame of klines for given symbol/interval from futures endpoint.
    Columns: open_time, open, high, low, close, volume, close_time, ...
    """
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades", "taker_base_vol", "taker_quote_vol", "ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def slope_of_series(series: pd.Series):
    """
    Compute normalized slope of series using linear regression.
    Returns slope_normalized = slope / mean_price  (approx % per candle)
    """
    y = series.values
    if len(y) < 3:
        return 0.0
    x = np.arange(len(y))
    res = linregress(x, y)
    slope = res.slope
    mean_price = np.mean(y) if np.mean(y) != 0 else 1.0
    return slope / mean_price

# ---------- Trend detection per timeframe ----------
def timeframe_trend(df: pd.DataFrame, price_col="close", vol_col="volume",
                    price_window=20, vol_recent=5, vol_prev=5,
                    slope_thresh=0.0004):
    """
    Decide trend on a timeseries chunk:
    - Use last `price_window` closes to compute slope normalized.
    - Use volume: avg recent vol (last vol_recent) compare to previous vol_prev.
    Returns: "up" | "down" | "sideway"
    slope_thresh: tuned threshold (normalized). Default ~0.04% per candle ~ small.
    """
    if len(df) < max(price_window, vol_recent + vol_prev + 1):
        return "sideway"
    prices = df[price_col].iloc[-price_window:]
    vol = df[vol_col]
    slope_norm = slope_of_series(prices)
    # volume check
    recent_vol_mean = vol.iloc[-vol_recent:].mean()
    prev_vol_mean = vol.iloc[-(vol_recent+vol_prev):-vol_recent].mean() if vol_prev>0 else recent_vol_mean
    vol_trend_ok = recent_vol_mean >= prev_vol_mean  # require non-decreasing volume to confirm
    # classify
    if slope_norm > slope_thresh and vol_trend_ok:
        return "up"
    if slope_norm < -slope_thresh and vol_trend_ok:
        return "down"
    return "sideway"

# ---------- Aggregate market trend across timeframes ----------
def detect_market_trend(symbol: str):
    """
    Detect overall market trend using 1d, 4h, 1h timeframes.
    Returns one of: "up", "down", "sideway"
    """
    tf_cfg = [
        ("1d", 50, 5),   # price_window, vol checks (these are passed to timeframe_trend)
        ("4h", 40, 5),
        ("1h", 40, 5),
    ]
    votes = {"up":0, "down":0, "sideway":0}
    for interval, price_window, vol_recent in tf_cfg:
        try:
            df = fetch_klines(symbol, interval, limit=max(200, price_window+20))
            t = timeframe_trend(df, price_window=price_window, vol_recent=vol_recent, vol_prev=5, slope_thresh=0.0004)
            votes[t] += 1
        except Exception as e:
            # if error, count as sideway to be conservative
            votes["sideway"] += 1
    # majority rule
    if votes["up"] >= 2:
        return "up"
    if votes["down"] >= 2:
        return "down"
    return "sideway"

# ---------- EMA crossover on M15 ----------
def ema(series: pd.Series, span: int):
    return series.ewm(span=span, adjust=False).mean()

def detect_m15_crossover(symbol: str):
    """
    Return:
      {"crossover": "BUY" | "SELL" | None, "ema7": float_last, "ema99": float_last, "prev_ema7":..., "prev_ema99":..., "close": last_close}
    Detects a crossing on the last candle (compare previous candle to current)
    """
    df = fetch_klines(symbol, "15m", limit=200)
    closes = df["close"].astype(float)
    ema7 = ema(closes, 7)
    ema99 = ema(closes, 99)
    if len(closes) < 3:
        return {"crossover": None}
    prev_e7 = float(ema7.iloc[-2])
    prev_e99 = float(ema99.iloc[-2])
    cur_e7 = float(ema7.iloc[-1])
    cur_e99 = float(ema99.iloc[-1])
    last_close = float(closes.iloc[-1])

    # detect cross up
    if prev_e7 <= prev_e99 and cur_e7 > cur_e99:
        return {"crossover":"BUY", "ema7":cur_e7, "ema99":cur_e99, "prev_ema7":prev_e7, "prev_ema99":prev_e99, "close": last_close}
    # detect cross down
    if prev_e7 >= prev_e99 and cur_e7 < cur_e99:
        return {"crossover":"SELL", "ema7":cur_e7, "ema99":cur_e99, "prev_ema7":prev_e7, "prev_ema99":prev_e99, "close": last_close}
    return {"crossover": None, "ema7":cur_e7, "ema99":cur_e99, "prev_ema7":prev_e7, "prev_ema99":prev_e99, "close": last_close}

# ---------- Combine rules -> signal ----------
def generate_signal(symbol: str, take_profit_pct: float = 0.02):
    """
    Returns a dict:
    {
      "signal": "LONG" | "SHORT" | None,
      "reason": str,
      "entry_price": float,
      "tp_price": float,
      "trend": "up"|"down"|"sideway",
      "crossover": {...}
    }
    """
    trend = detect_market_trend(symbol)
    cross = detect_m15_crossover(symbol)

    if cross.get("crossover") is None:
        return {"signal": None, "reason": "No EMA crossover on M15", "trend": trend, "crossover": cross}

    if trend == "sideway":
        return {"signal": None, "reason": "Market is sideway on higher TFs", "trend": trend, "crossover": cross}

    # map
    if cross["crossover"] == "BUY" and trend == "up":
        entry = cross["close"]
        tp = entry * (1.0 + float(take_profit_pct))
        return {"signal":"LONG", "reason":"EMA7 crossed above EMA99 on M15 and trend is UP", "entry_price": entry, "tp_price": tp, "trend":trend, "crossover": cross}
    if cross["crossover"] == "SELL" and trend == "down":
        entry = cross["close"]
        tp = entry * (1.0 - float(take_profit_pct))
        return {"signal":"SHORT", "reason":"EMA7 crossed below EMA99 on M15 and trend is DOWN", "entry_price": entry, "tp_price": tp, "trend":trend, "crossover": cross}

    return {"signal": None, "reason":"Crossover direction not aligned with higher-timeframe trend", "trend":trend, "crossover": cross}

def fetch_klines1(symbol, interval="15m", limit=500):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","qav","num_trades","taker_base_vol","taker_quote_vol","ignore"
    ])
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df


def detect_m15_crossover(symbol):
    df = fetch_klines1(symbol, "15m", 200)
    close = df["close"].astype(float).values

    ema7 = talib.EMA(close, timeperiod=7)
    ema99 = talib.EMA(close, timeperiod=99)

    prev7, prev99 = ema7[-2], ema99[-2]
    cur7, cur99 = ema7[-1], ema99[-1]
    last_close = close[-1]
    
    rsi = talib.RSI(df['close'].values, timeperiod=14)
    if rsi[-1] > 70:
        print("RSI cao, tránh Long")
    elif rsi[-1] < 30:
        print("RSI thấp, tránh Short")

    macd, macd_signal, macd_hist = talib.MACD(df['close'].values, fastperiod=12, slowperiod=26, signalperiod=9)
    if macd[-1] > macd_signal[-1]:
        print("MACD bullish")

    if prev7 <= prev99 and cur7 > cur99:
        return {"crossover": "BUY", "close": last_close, "ema7": cur7, "ema99": cur99}
    elif prev7 >= prev99 and cur7 < cur99:
        return {"crossover": "SELL", "close": last_close, "ema7": cur7, "ema99": cur99}
    else:
        return {"crossover": None, "close": last_close, "ema7": cur7, "ema99": cur99}



# ---------- Example usage ----------
if __name__ == "__main__":
    symbol = "WLDUSDT"
    sig = generate_signal(symbol)
    print("Signal:", sig)
    # If you want to execute, build order payload to feed your order_client
    if sig["signal"] == "LONG":
        # example: use usdt exposure (you decide amount/leverage)
        print("Suggested TP price (2%):", sig["tp_price"])
    elif sig["signal"] == "SHORT":
        print("Suggested TP price (2%):", sig["tp_price"])
    else:
        print("No trade suggested:", sig["reason"])
