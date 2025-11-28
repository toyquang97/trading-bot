from include import *


SYMBOL = 'BTCUSDT'

INTERVAL = Client.KLINE_INTERVAL_1MINUTE

DAYS_AGO = 3

# OUTPUT_FILENAME -> lưu vào folder `data` bên trong project
OUTPUT_FILENAME = os.path.join(os.path.dirname(__file__), "data", f'{SYMBOL}_{INTERVAL}_{DAYS_AGO}d.csv')



# --- New: fetch range helper ---
def _interval_to_millis(interval: str) -> int:
    """Convert Binance interval string to milliseconds."""
    unit = interval[-1]
    val = int(interval[:-1])
    if unit == "m":
        return val * 60 * 1000
    if unit == "h":
        return val * 60 * 60 * 1000
    if unit == "d":
        return val * 24 * 60 * 60 * 1000
    if unit == "w":
        return val * 7 * 24 * 60 * 60 * 1000
    if unit == "M":
        return val * 30 * 24 * 60 * 60 * 1000
    # fallback
    return val * 60 * 1000


def fetch_futures_data_by_range(symbol: str,
                               interval: str,
                               start_dt,
                               end_dt,
                               filename: str = None,
                               futures: bool = True,
                               tz: str = "Asia/Ho_Chi_Minh"):
    """
    Fetch klines between start_dt and end_dt (inclusive) and save to CSV.
    start_dt / end_dt can be datetime or string (ISO / 'YYYY-MM-DD').
    If filename is None, it will be placed under ./data/<symbol>_<interval>_<start>_to_<end>.csv
    """
    # parse datetimes
    start = pd.to_datetime(start_dt)
    end = pd.to_datetime(end_dt)

    # make end inclusive to end of day if no time component provided
    if start.tzinfo is None:
        start = start.tz_localize("UTC").tz_convert("UTC")
    if end.tzinfo is None and end.time() == datetime.min.time():
        # user passed a date only -> include whole day
        end = (end + timedelta(days=1) - timedelta(milliseconds=1))
    if end.tzinfo is None:
        end = end.tz_localize("UTC").tz_convert("UTC")

    # convert to milliseconds in UTC for API
    start_ms = int(start.tz_convert("UTC").value // 10**6)
    end_ms = int(end.tz_convert("UTC").value // 10**6)

    limit = 1500
    interval_ms = _interval_to_millis(interval)
    all_rows = []

    # expected number of candles (used for progress)
    expected_candles = max(1, int((end_ms - start_ms) // interval_ms) + 1)
    fetched_candles = 0

    curr_start = start_ms
    while curr_start <= end_ms:
        # request chunk
        try:
            if futures:
                chunk = client.futures_klines(symbol=symbol, interval=interval, startTime=curr_start, endTime=end_ms, limit=limit)
            else:
                chunk = client.get_klines(symbol=symbol, interval=interval, startTime=curr_start, endTime=end_ms, limit=limit)
        except Exception as e:
            raise

        if not chunk:
            break

        all_rows.extend(chunk)
        fetched_candles += len(chunk)

        # update progress
        progress = min(100.0, fetched_candles / expected_candles * 100.0)
        print(f"\rFetching {symbol} {interval}: {progress:.1f}% ({fetched_candles}/{expected_candles} candles)", end="", flush=True)

        # advance: last open_time + interval_ms
        last_open = int(chunk[-1][0])
        next_start = last_open + interval_ms
        if next_start <= curr_start:
            # avoid infinite loop
            break
        curr_start = next_start

        # small sleep could be added here if you hit rate limits

    # ensure newline after progress
    print()

    if not all_rows:
        # return empty dataframe
        df = pd.DataFrame()
    else:
        cols = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ]
        df = pd.DataFrame(all_rows, columns=cols)
        # convert times to datetime (UTC -> convert to tz)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_convert(tz)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True).dt.tz_convert(tz)
        # numeric cast
        for c in ("open","high","low","close","volume","quote_asset_volume","taker_buy_base","taker_buy_quote"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        if "ignore" in df.columns:
            df = df.drop(columns=["ignore"])

    # default filename if not provided
    if filename is None:
        start_label = pd.to_datetime(start_ms, unit="ms").strftime("%Y%m%d")
        end_label = pd.to_datetime(end_ms, unit="ms").strftime("%Y%m%d")
        filename = os.path.join(os.path.dirname(__file__), "data", f"{symbol}_{interval}_{start_label}_to_{end_label}.csv")

    # ensure directory exists
    dirpath = os.path.dirname(filename)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath, exist_ok=True)

    # save
    df.to_csv(filename, index=False, encoding="utf-8")
    return {"ok": True, "rows": len(df), "filename": filename}



# --- Thực thi Hàm ---
# fetch_futures_data_by_range("BTCUSDT", "15m", "2025-11-01", "2025-11-20")
# Gọi hàm để lấy dữ liệu 3 ngày gần nhất theo khung 15 phút



# fetch_full_futures_data_to_csv(

#     symbol=SYMBOL,

#     interval=INTERVAL,

#     days_ago=DAYS_AGO, # Lấy dữ liệu 3 ngày gần nhất

#     filename=OUTPUT_FILENAME

# )



# fetch_and_save_futures_data_to_csv(

#     symbol=SYMBOL,

#     interval=INTERVAL,

#     days_ago=3, # Chỉ định lấy dữ liệu 3 ngày gần nhất

#     filename=OUTPUT_FILENAME

# )