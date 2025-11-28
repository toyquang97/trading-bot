import os
import time
import requests
from datetime import datetime, timedelta
import pandas as pd

# helper: convert interval like "1m","15m","1h","1d" to milliseconds
def _interval_to_millis(interval: str) -> int:
    unit = interval[-1]
    val = int(interval[:-1])
    if unit == "m":
        return val * 60_000
    if unit == "h":
        return val * 60 * 60_000
    if unit == "d":
        return val * 24 * 60 * 60_000
    if unit == "w":
        return val * 7 * 24 * 60 * 60_000
    if interval.endswith("M"):  # months, capital M
        return val * 30 * 24 * 60 * 60_000
    raise ValueError(f"Unsupported interval: {interval}")

def _binance_klines_public(symbol: str, interval: str, startTime: int = None, endTime: int = None, limit: int = 1500, futures: bool = True, timeout: int = 10):
    """
    Call Binance public klines endpoint (no API key).
    Returns parsed JSON (list of klines).
    """
    if futures:
        base = "https://fapi.binance.com/fapi/v1/klines"
    else:
        base = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if startTime is not None:
        params["startTime"] = int(startTime)
    if endTime is not None:
        params["endTime"] = int(endTime)
    resp = requests.get(base, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

def fetch_futures_data_by_range(
    symbol: str,
    interval: str,
    start_dt,
    end_dt,
    filename: str = None,
    futures: bool = True,
    tz: str = "Asia/Ho_Chi_Minh",
    client=None,
    limit: int = 1500,
    sleep_on_rate_limit: float = 0.3,
    max_retries: int = 5,
):
    """
    Lấy klines giữa start_dt và end_dt (inclusive) và lưu CSV.
    - start_dt / end_dt: datetime hoặc string (ISO / 'YYYY-MM-DD' / 'YYYY-MM-DD HH:MM:SS')
    - Nếu filename=None -> mặc định lưu vào ./data/<symbol>_<interval>_<start>_to_<end>.csv
    - Nếu client được truyền (python-binance Client) thì dùng client; nếu client=None thì gọi public REST endpoints (LIVE data).
    - Trả về dict {"ok": True, "rows": n, "filename": path, "df": df}
    """

    # parse datetimes
    start = pd.to_datetime(start_dt)
    end = pd.to_datetime(end_dt)

    # if end is date-only (time 00:00:00) -> include whole day
    if end.time() == datetime.min.time():
        end = end + timedelta(days=1) - timedelta(milliseconds=1)

    # Normalize timezone: treat naive times as user tz, then convert to UTC for API
    if start.tzinfo is None:
        start = start.tz_localize(tz)
    if end.tzinfo is None:
        end = end.tz_localize(tz)

    start_utc = start.tz_convert("UTC")
    end_utc = end.tz_convert("UTC")
    start_ms = int(start_utc.value // 10**6)
    end_ms = int(end_utc.value // 10**6)

    if start_ms > end_ms:
        raise ValueError("start_dt must be before end_dt")

    interval_ms = _interval_to_millis(interval)
    # clamp limit to Binance allowed max (safety)
    if limit <= 0 or limit > 1500:
        limit = 1500

    all_rows = []
    fetched_candles = 0
    expected_candles = max(1, int((end_ms - start_ms) // interval_ms) + 1)

    curr_start = start_ms
    retries = 0

    while curr_start <= end_ms:
        try:
            if client is not None:
                # use python-binance client (may require API key for other endpoints but klines usually public)
                if futures:
                    chunk = client.futures_klines(symbol=symbol, interval=interval, startTime=curr_start, endTime=end_ms, limit=limit)
                else:
                    chunk = client.get_klines(symbol=symbol, interval=interval, startTime=curr_start, endTime=end_ms, limit=limit)
            else:
                # use public REST endpoint (live data)
                chunk = _binance_klines_public(symbol=symbol, interval=interval, startTime=curr_start, endTime=end_ms, limit=limit, futures=futures)
        except Exception as e:
            retries += 1
            if retries > max_retries:
                raise
            backoff = sleep_on_rate_limit * (2 ** (retries - 1))
            print(f"\nRequest error: {e}. retrying in {backoff:.1f}s ({retries}/{max_retries})")
            time.sleep(backoff)
            continue

        retries = 0
        if not chunk:
            break

        all_rows.extend(chunk)
        fetched_candles += len(chunk)

        # progress
        progress = min(100.0, fetched_candles / expected_candles * 100.0)
        print(f"\rFetching {symbol} {interval}: {progress:.1f}% ({fetched_candles}/{expected_candles} candles)", end="", flush=True)

        # advance cursor: last_open + interval_ms
        last_open = int(chunk[-1][0])
        next_start = last_open + interval_ms
        if next_start <= curr_start:
            # safety break to avoid infinite loop
            break
        curr_start = next_start

        # gentle sleep (avoid rate limit)
        time.sleep(sleep_on_rate_limit)

    print()

    # build dataframe
    if not all_rows:
        df = pd.DataFrame()
    else:
        cols = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ]
        df = pd.DataFrame(all_rows, columns=cols)
        # convert times to datetime (UTC -> user tz)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_convert(tz)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True).dt.tz_convert(tz)
        # numeric cast
        for c in ("open","high","low","close","volume","quote_asset_volume","taker_buy_base","taker_buy_quote"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if "ignore" in df.columns:
            df = df.drop(columns=["ignore"])

    # default filename if not provided
    if filename is None:
        # default to the uploaded path if exists (developer note) else create under ./data
        default_uploaded = "/mnt/data/BTCUSDT_4h_20251101_to_20251120.csv"
        if os.path.exists(default_uploaded):
            filename = default_uploaded
        else:
            start_label = start.tz_convert(tz).strftime("%Y%m%d_%H%M")
            end_label = end.tz_convert(tz).strftime("%Y%m%d_%H%M")
            filename = os.path.join(os.getcwd(), "data", f"{symbol}_{interval}_{start_label}_to_{end_label}.csv")

    # ensure directory exists
    dirpath = os.path.dirname(filename)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath, exist_ok=True)

    # save CSV
    df.to_csv(filename, index=False, encoding="utf-8")

    return {"ok": True, "rows": len(df), "filename": filename, "df": df}

res = fetch_futures_data_by_range("BTCUSDT", "1m", "2025-01-01", "2025-03-01", client=None, futures=True)
print(res["filename"], res["rows"])