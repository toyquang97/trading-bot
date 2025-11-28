# strategy_mtf.py
"""
Strategy module that:
- Accepts full 1m OHLCV DataFrame (index = DatetimeIndex)
- Resamples to requested MTFs and precomputes indicators (EMA, RSI)
- Generates signals aligned to 1m index and returns signals_df with columns:
    - signal_side: 'BUY' / 'SELL' / NaN
    - size: optional absolute units (float) OR
    - risk_pct: optional fraction of current capital to allocate (float in (0,1])
    - tp_price: optional target price
    - sl_price: optional stop price
Notes:
- If both size and risk_pct provided, engine will prefer size.
- Implementation uses talib for indicators.
"""
import pandas as pd
import numpy as np
import talib
from typing import List, Optional
 
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
 
def precompute_mtf_indicators(df_1m: pd.DataFrame, mtf_timeframes: List[str]) -> dict:
    """
    Resample df_1m to each timeframe and compute indicators once.
    Returns dict: {tf: df_tf_with_indicators}
    """
    mtf = {}
    # make lowercase columns for calculation convenience
    tmp = df_1m.copy()
    tmp.columns = [c.lower() for c in tmp.columns]
    if not isinstance(tmp.index, pd.DatetimeIndex):
        raise TypeError("precompute_mtf_indicators: df_1m index must be DatetimeIndex")
    for tf in mtf_timeframes:
        df_tf = resample_data(tmp, tf)
        # compute indicators (example set)
        # talib functions require np.array float
        close = df_tf['Close'].values
        # compute EMA7, EMA99, RSI14
        df_tf['ema7'] = talib.EMA(close, timeperiod=7)
        df_tf['ema99'] = talib.EMA(close, timeperiod=99)
        df_tf['rsi14'] = talib.RSI(close, timeperiod=14)
        mtf[tf] = df_tf
    return mtf
 
def generate_signals(df_1m: pd.DataFrame,
                     mtf_timeframes: Optional[List[str]] = None,
                     base_risk_pct: float = 0.01) -> pd.DataFrame:
    """
    Main entrypoint for strategy.
    - df_1m: DataFrame indexed by 1-minute DatetimeIndex. Columns must include Open/High/Low/Close/Volume
    - mtf_timeframes: list like ['15T','1H','4H']
    - base_risk_pct: default risk fraction used when creating risk_pct for signals if not specified
    Returns signals_df indexed by the same 1m index, with columns:
    signal_side, size, risk_pct, tp_price, sl_price
    """
    if mtf_timeframes is None:
        mtf_timeframes = ['15T','1H','4H']
 
    df = df_1m.copy()
    # normalize columns
    # allow both 'Close' and 'close' style
    df.columns = [c.capitalize() for c in df.columns]
    if 'Close' not in df.columns:
        raise ValueError("generate_signals: df_1m must contain Close column")
 
    # prepare signals dataframe
    signals = pd.DataFrame(index=df.index)
    signals['signal_side'] = pd.Series(index=df.index, dtype=object)
    signals['note'] = pd.Series(index=df.index, dtype=object)
    signals['size'] = np.nan
    signals['risk_pct'] = np.nan
    signals['tp_price'] = np.nan
    signals['sl_price'] = np.nan
 
 
    # Precompute indicators on each MTF
    mtf = precompute_mtf_indicators(df, mtf_timeframes)
 
    # Example strategy:
    # - Determine trend on 4H: ema7 > ema99 => bull
    # - Detect EMA7 x EMA99 cross on M15 as signal
    # - Confirm with 1m RSI (rsi14 <= 50 for buy confirmation on cross up)
    # - Emit signal at the last 1m bar inside the M15 candle (so engine executes at that 1m timestamp)
    m15 = mtf.get('15T')
    h4 = mtf.get('4H')
 
    if m15 is None:
        # nothing to do if M15 not available
        return signals
 
    # prepare cross detection on M15
    m15['ema7_prev'] = m15['ema7'].shift(1)
    m15['ema99_prev'] = m15['ema99'].shift(1)
    m15['cross_up'] = (m15['ema7_prev'] <= m15['ema99_prev']) & (m15['ema7'] > m15['ema99'])
    m15['cross_down'] = (m15['ema7_prev'] >= m15['ema99_prev']) & (m15['ema7'] < m15['ema99'])
 
    # iterate M15 candles where cross happened
    for ts, row in m15.iterrows():
        if not (row.get('cross_up', False) or row.get('cross_down', False)):
            continue
 
        # find H4 trend at this timestamp (last H4 candle <= ts)
        trend_is_bull = None
        try:
            h4_slice = h4.loc[:ts]
            if not h4_slice.empty:
                last_h4 = h4_slice.iloc[-1]
                trend_is_bull = (last_h4['ema7'] > last_h4['ema99'])
        except Exception:
            trend_is_bull = None
 
        # map M15 candle to 1m bars: ts .. ts + 15min -1min
        start = ts
        end = ts + pd.Timedelta(minutes=15)  # exclusive
        slice_1m = df.loc[start:end - pd.Timedelta(minutes=1)]
        if slice_1m.empty:
            continue
        last_1m = slice_1m.iloc[-1]
        # compute 1m RSI up to that last_1m (causal)
        idx_pos = df.index.get_loc(last_1m.name)
        if idx_pos + 1 < 15:
            # not enough history for RSI14, skip
            continue
        closes_until = df['Close'].values[:idx_pos + 1]
        rsi_1m = talib.RSI(closes_until, timeperiod=14)[-1]
        # Build signal
        entry_price = last_1m['Close']
       
        # 🚨 BƯỚC SỬA ĐỔI TP/SL 🚨
       
        # Đặt tỷ lệ cố định 4% TP / 2% SL (R:R 2:1)
        TP_FACTOR = 0.04  # 4%
        SL_FACTOR = 0.02  # 2%
 
        if row['cross_up'] and (trend_is_bull is None or trend_is_bull) and rsi_1m <= 50:
            # BUY signal (Long Entry)
            sig_ts = last_1m.name
            signals.at[sig_ts, 'signal_side'] = 'BUY'
           
            signals.at[sig_ts, 'risk_pct'] = base_risk_pct
           
            # CẬP NHẬT TP/SL CHO LONG:
            signals.at[sig_ts, 'tp_price'] = entry_price * (1 + TP_FACTOR) # Giá TP cao hơn
            signals.at[sig_ts, 'sl_price'] = entry_price * (1 - SL_FACTOR) # Giá SL thấp hơn
           
            signals.at[sig_ts, 'note'] = 'm15_cross_up_confirmed_by_1m_rsi'
           
        elif row['cross_down'] and (trend_is_bull is None or not trend_is_bull) and rsi_1m >= 50:
            # SELL signal (Short Entry)
            sig_ts = last_1m.name
            signals.at[sig_ts, 'signal_side'] = 'SELL'
            signals.at[sig_ts, 'risk_pct'] = base_risk_pct
           
            # CẬP NHẬT TP/SL CHO SHORT:
            signals.at[sig_ts, 'tp_price'] = entry_price * (1 - TP_FACTOR) # Giá TP thấp hơn
            signals.at[sig_ts, 'sl_price'] = entry_price * (1 + SL_FACTOR) # Giá SL cao hơn
           
            signals.at[sig_ts, 'note'] = 'm15_cross_down_confirmed_by_1m_rsi'
 
    # drop rows with no signal to reduce size (optional) - keep full index but NaNs allowed
    return signals