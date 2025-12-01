from dotenv import load_dotenv
import os
from pprint import pprint
import pandas as pd
import datetime
import talib
import json
import time
from datetime import datetime
import pytz # Thư viện để quản lý múi giờ
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import altair as alt
from scipy.signal import find_peaks
import numpy as np
import argparse
from datetime import timedelta
from typing import List
from typing import Optional
from pandas.tseries.frequencies import to_offset
from pathlib import Path

def get_data_path(fname: str) -> Path:
    # find data dir relative to this file
    this_file = Path(__file__).resolve()
    for parent in this_file.parents[:6]:
        cand = parent / "data"
        if cand.is_dir():
            p = cand / fname
            if p.is_file():
                return p.resolve()
            # if not file but dir exists return dir for caller to inspect
            return cand.resolve()
    # fallback cwd
    if (Path.cwd() / "data").is_dir():
        return (Path.cwd() / "data" / fname).resolve()
    raise FileNotFoundError(f"Could not find '{fname}' in any data directories.")


def clean_ohlc(df_raw: pd.DataFrame, timeframe: str = '1min') -> pd.DataFrame:
    """
    Chuẩn hoá OHLC cho mọi khung thời gian:
    timeframe ví dụ: '1min', '5min', '15min', '30min', '1h', '4h'
    """
    df = df_raw.copy()

    df.columns = [c.lower() for c in df.columns]
    # Convert open_time -> datetime
    df['open_time'] = pd.to_datetime(df['open_time'], errors='coerce')
    df = df.dropna(subset=['open_time'])

    # Set index
    df = df.set_index('open_time')
    df = df.sort_index()

    # Floor index theo timeframe
    df.index = df.index.floor(timeframe)

    # Capitalize column names
    df.columns = [c.lower() for c in df.columns]

    return df


def _normalize_tf_alias(tf: str) -> str:
    """
    Convert deprecated freq formats → new recommended ones.
    '15T' → '15min'
    '1H'  → '1h'
    """
    tf = str(tf).lower().strip()

    # minute formats
    if tf.endswith("t"):
        return tf[:-1] + "min"
    if "min" in tf:
        return tf

    # hour
    if tf.endswith("h"):
        return tf
    if tf.endswith("hour"):
        return tf.replace("hour", "h")

    # day
    if tf.endswith("d"):
        return tf
    if tf.endswith("day"):
        return tf.replace("day", "d")

    return tf


def resample_data11(df_1m: pd.DataFrame, tf: str) -> pd.DataFrame:

    """
    Resample OHLCV từ 1 phút theo chuẩn Binance Futures.
    - Các timeframe <= 1H dùng mốc 00:00 (KHÔNG offset)
    - Các timeframe >= 4H và 1D, 1W, 1M dùng mốc 00:00 UTC => offset 7H (giờ VN)
    1m '1T'

    3m '3T'

    5m '5T'

    15m '15T'

    30m '30T'

    1h '1H'

    2h '2H'
    4h '4H'

    6h '6H'

    8h '8H'

    12h '12H'

    1D '1D'

    1W '1W'

    1M '1M'
    Yêu cầu: df_1m.index phải là DatetimeIndex (tz-aware hoặc naive đều được).
    """

    """
    Resample 1m -> tf for Binance-style CSV. 
    return_label: 'left' to return start-of-interval timestamps (common in Binance CSV),
                  'right' to return end-of-interval timestamps.
    """
    tf_norm = tf.upper().replace('M','T')  # 15m -> 15T
    # decide offset for >=4H / 1D per Binance
    no_offset = ['1T','3T','5T','15T','30T','1H','2H']
    offset = None if tf_norm in no_offset else '7H'

    if offset is None:
        ohlc = df_1m['close'].resample(tf_norm, label='right', closed='right').ohlc()
        vol  = df_1m['volume'].resample(tf_norm, label='right', closed='right').sum()
    else:
        ohlc = df_1m['close'].resample(tf_norm, label='right', closed='right',
                                       origin='start_day', offset='7H').ohlc()
        vol  = df_1m['volume'].resample(tf_norm, label='right', closed='right',
                                        origin='start_day', offset='7H').sum()

    out = pd.DataFrame(index=ohlc.index)
    out['open'] = ohlc['open']; out['high'] = ohlc['high']
    out['low']  = ohlc['low'];  out['close'] = ohlc['close']
    out['volume']= vol

    
    # convert end-of-interval index -> start-of-interval index
    # (works when above was computed with label='right')
    period = pd.Timedelta(pd.tseries.frequencies.to_offset(tf_norm))
    out.index = out.index - period

    return out


def _normalize_tf(tf: str) -> str:
    s = str(tf).strip().upper()
    # keep '1D','1W','1M' as-is; convert minutes '15M' -> '15T' for pandas
    if s.endswith('M') and not s.endswith('D') and not s.endswith('W'):
        # '15M' -> '15T'
        s = s[:-1] + 'T'
    return s

def resample_data(
    df_1m: pd.DataFrame,
    tf: str,
    day_start_hour: int = 7,
    match_open_with_1m: bool = True,
    volume_col_candidates: Optional[list] = None
) -> pd.DataFrame:
    """
    Resample 1m OHLCV -> timeframe `tf` following Binance conventions.
    - df_1m: must have DatetimeIndex and contain at least 'open','high','low','close' (case-insensitive).
             Prefer also 'volume'.
    - tf: string like '15m','15T','30m','1H','4h','1D','1W','1M'.
    - day_start_hour: local hour that corresponds to 00:00 UTC (7 for UTC+7 VN).
    - return_label: 'start' -> return start-of-interval timestamps (like Binance CSV open_time),
                    'end'   -> return end-of-interval timestamps (pandas label='right' style).
    - match_open_with_1m: if True and 1m contains exact start timestamp, use 1m 'open' to overwrite aggregated open
    - volume_col_candidates: list of possible volume column names to detect (defaults to ['volume','vol'])
    Returns DataFrame indexed by timestamps with columns: ['open','high','low','close','volume'].
    """

    if volume_col_candidates is None:
        volume_col_candidates = ['volume', 'vol']

    if not isinstance(df_1m.index, pd.DatetimeIndex):
        raise TypeError("df_1m.index must be a DatetimeIndex")

    tf_norm = _normalize_tf(tf)

    # decide which TFs need offset: <=2H no offset; >=4H+1D need offset (Binance convention)
    no_offset = {'1T','3T','5T','15T','30T','1H','2H'}
    needs_offset = tf_norm not in no_offset

    # normalize column names to lowercase, keep original mapping for later restore if needed
    df = df_1m.copy()
    orig_cols = df.columns.tolist()
    colmap = {c.lower(): c for c in orig_cols}
    df.columns = [c.lower() for c in df.columns]

    if 'close' not in df.columns:
        raise TypeError("df_1m must contain 'close' column (case-insensitive)")

    # choose resample params
    if needs_offset:
        ohlc = df['close'].resample(
            tf_norm, label='right', closed='right', origin='start_day', offset=f'{day_start_hour}H'
        ).ohlc()
        vol = None
        # try detect volume column
        for vc in volume_col_candidates:
            if vc in df.columns:
                vol = df[vc].resample(tf_norm, label='right', closed='right', origin='start_day', offset=f'{day_start_hour}H').sum()
                break
        if vol is None:
            vol = pd.Series(index=ohlc.index, dtype=float)
    else:
        ohlc = df['close'].resample(tf_norm, label='right', closed='right').ohlc()
        vol = None
        for vc in volume_col_candidates:
            if vc in df.columns:
                vol = df[vc].resample(tf_norm, label='right', closed='right').sum()
                break
        if vol is None:
            vol = pd.Series(index=ohlc.index, dtype=float)

    out = pd.DataFrame(index=ohlc.index)
    out['open'] = ohlc['open']
    out['high'] = ohlc['high']
    out['low'] = ohlc['low']
    out['close'] = ohlc['close']
    out['volume'] = vol
    out.index.name = 'time'   # currently end-of-interval timestamps

    # convert to start-of-interval if user requested

    period = to_offset(tf_norm)
    out.index = out.index - period
    out.index.name = 'open_time'  # match Binance CSV open_time naming

    # TRY to match open exactly using 1m open at start timestamp (if requested)
    if match_open_with_1m:
        # find timestamps that exist in 1m index and in resample index
        common = out.index.intersection(df.index)
        # If df index timezone differs, ensure comparability (both tz-aware equal)
        for t in common:
            # use lowercase df columns (original mapping kept)
            if 'open' in df.columns:
                out.at[t, 'open'] = df.at[t, 'open']

    # restore column labels to standard lower-case (open,high,low,close,volume)
    return out

# -----------------------
# Example usage:
# res_4h = resample_general_binance(df_1m, '4H', day_start_hour=7, return_label='start')
# res_15m = resample_general_binance(df_1m, '15T', return_label='end')
