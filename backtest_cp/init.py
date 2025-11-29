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


def resample_data(data_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Correct & stable resample:
    - ALWAYS returns lowercase: open/high/low/close/volume
    - Use label='right', closed='right' → matches M15->1m mapping
    - Corrects deprecated 'T' → 'min'
    """
    df = data_1m.copy()
    df.columns = df.columns.str.lower()

    # detect time column if index is not datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        for name in ["open_time", "timestamp", "time"]:
            if name in df.columns:
                df[name] = pd.to_datetime(df[name])
                df = df.set_index(name)
                break

    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("resample_data: index must be DatetimeIndex")

    df.index = df.index.floor("1min")

    tf = _normalize_tf_alias(timeframe)

    ohlcv = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }

    # RIGHT EDGE (important for your strategy logic)
    rs = df.resample(tf, label="left", closed="left").agg(ohlcv)

    rs = rs.dropna(subset=["close"])

    # keep everything lowercase to avoid KeyError
    rs.columns = rs.columns.str.lower()

    return rs

