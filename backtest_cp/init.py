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


# replace existing resample_data with this robust version
def _normalize_tf_alias(tf: str) -> str:
    tf = str(tf)
    # common conversions 'T'->'min', 'H'->'h'
    if tf.endswith('T'):
        return tf[:-1] + 'min'
    if tf.endswith('H'):
        return tf[:-1] + 'h'
    return tf
 
def resample_data(data_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Robust resample:
    - Normalize timeframe aliases ('15T' -> '15min', '1H' -> '1h')
    - Use label='left', closed='left' for deterministic bin alignment
    - Ensure index is datetime (and floored to minute)
    """
    # prepare data
    data = data_1m.copy()
    data.columns = data.columns.str.lower()
 
    # If time column present, set index
    if 'open_time' in data.columns:
        data['open_time'] = pd.to_datetime(data['open_time'])
        data.set_index('open_time', inplace=True)
 
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("Index must be DatetimeIndex for resampling")
 
    # floor to 1 minute to avoid sub-minute offsets
    data.index = data.index.floor('1min')
 
    # normalize timeframe alias
    tf = _normalize_tf_alias(timeframe)
 
    ohlcv_agg = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }
    valid_agg = {col: func for col, func in ohlcv_agg.items() if col in data.columns}
 
    # use explicit label/closed so bins align predictably
    resampled = data.resample(tf, label='left', closed='left').agg(valid_agg)
 
    # drop rows with NaN (incomplete candles)
    resampled = resampled.dropna()
 
    # restore capitalization to match remainder code (Open/High/...)
    resampled.columns = [c.capitalize() for c in resampled.columns]
    return resampled