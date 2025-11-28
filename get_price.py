from dotenv import load_dotenv
import os
from binance.client import Client
import pandas as pd
from load_env import *
# load .env next to this file



def get_klines_df(symbol: str, interval: str = "1m", limit: int = 500, futures: bool = True, tz: str = "UTC", make_naive: bool = False) -> pd.DataFrame:
    """
    Fetch klines and return a pandas.DataFrame.
    tz: timezone string e.g. "UTC" or "Asia/Ho_Chi_Minh". If None, don't localize/convert.
    make_naive: if True, convert to tz then drop tz info (return naive datetimes in requested tz).
    """
    if futures:
        raw = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    else:
        raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)

    cols = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "num_trades",
        "taker_buy_base",
        "taker_buy_quote",
        "ignore",
    ]
    df = pd.DataFrame(raw, columns=cols)

    # convert types
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")

    # timezone handling: Binance timestamps are UTC
    if tz:
        # localize as UTC first, then convert to requested tz
        df["open_time"] = df["open_time"].dt.tz_localize("UTC").dt.tz_convert(tz)
        df["close_time"] = df["close_time"].dt.tz_localize("UTC").dt.tz_convert(tz)
        if make_naive:
            df["open_time"] = df["open_time"].dt.tz_convert(tz).dt.tz_localize(None)
            df["close_time"] = df["close_time"].dt.tz_convert(tz).dt.tz_localize(None)

    for c in ("open", "high", "low", "close", "volume", "quote_asset_volume", "taker_buy_base", "taker_buy_quote"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # drop unused column
    if "ignore" in df.columns:
        df = df.drop(columns=["ignore"])

    return df


# backward-compatible wrapper for existing code that used get_btc_price_1m
def get_btc_price_1m(limit: int = 500, futures: bool = True) -> pd.DataFrame:
    """Compatibility wrapper: fetch BTCUSDT 1m klines."""
    return get_klines_df("BTCUSDT", interval="1m", limit=limit, futures=futures)
