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
from init import *
 
# replace existing resample_data with this robust version
 
def precompute_mtf_indicators(df_1m: pd.DataFrame, mtf_timeframes: List[str]) -> dict:
    # Hàm này được giữ nguyên
    mtf = {}
    tmp = df_1m.copy()
    tmp.columns = [c.lower() for c in tmp.columns]
    if not isinstance(tmp.index, pd.DatetimeIndex):
        raise TypeError("precompute_mtf_indicators: df_1m index must be DatetimeIndex")
    for tf in mtf_timeframes:
        # Giả định resample_data(tmp, tf) đã được sửa lỗi index
        df_tf = resample_data(tmp, tf)
        close = df_tf['Close'].values
        df_tf['ema7'] = talib.EMA(close, timeperiod=7)
        df_tf['ema99'] = talib.EMA(close, timeperiod=99)
        df_tf['rsi14'] = talib.RSI(close, timeperiod=14)
        mtf[tf] = df_tf
    return mtf
 
 
# strategy_mtf.py (Phiên bản đã sửa đổi cho chiến thuật RSI M15)
 
# ... (Hàm resample_data và precompute_mtf_indicators giữ nguyên) ...
 
def generate_signals(df_1m: pd.DataFrame,
                     mtf_timeframes: Optional[List[str]] = None,
                     base_risk_pct: float = 0.01) -> pd.DataFrame:
 
    # if mtf_timeframes is None:
    #     # Chúng ta chỉ cần M15 cho chiến thuật này
    mtf_timeframes = ['15T']
    df = df_1m.copy()
    df.columns = [c.capitalize() for c in df.columns]
    # ... (Khởi tạo signals DataFrame giữ nguyên) ...
        # prepare signals dataframe
    signals = pd.DataFrame(index=df.index)
    signals['signal_side'] = pd.Series(index=df.index, dtype=object)
    signals['note'] = pd.Series(index=df.index, dtype=object)
    signals['size'] = np.nan
    signals['risk_pct'] = np.nan
    signals['tp_price'] = np.nan
    signals['sl_price'] = np.nan
    # Precompute indicators on each MTF (chỉ chạy trên M15)
    mtf = precompute_mtf_indicators(df, mtf_timeframes)
 
    m15 = mtf.get('15T')
   
    if m15 is None:
        return signals
 
    # Chuẩn bị để phát hiện tín hiệu: RSI cắt vùng 30 hoặc 60
 
    # 1. Tính RSI M15 của nến trước đó (dùng cho tín hiệu cắt)
    m15['rsi14_prev'] = m15['rsi14'].shift(1)
 
    # 2. Phát hiện Tín hiệu Mua (RSI cắt xuống dưới 30)
    # Tín hiệu Mua: nến trước (prev) >= 30 VÀ nến hiện tại (curr) < 30
    m15['signal_buy'] = (m15['rsi14_prev'] >= 15) & (m15['rsi14'] < 15)
 
    # 3. Phát hiện Tín hiệu Bán (RSI cắt lên trên 60)
    # Tín hiệu Bán: nến trước (prev) <= 60 VÀ nến hiện tại (curr) > 60
    m15['signal_sell'] = (m15['rsi14_prev'] <= 80) & (m15['rsi14'] > 80)
   
    # Thiết lập TP/SL 4%/2% (R:R 2:1) theo yêu cầu trước đó
    TP_FACTOR = 0.04
    SL_FACTOR = 0.02
   
    # Lặp qua các nến M15 có tín hiệu
    for ts, row in m15.iterrows():
        if not (row.get('signal_buy', False) or row.get('signal_sell', False)):
            continue
 
        # Map nến M15 (ts) tới thanh nến 1M cuối cùng trong nhóm
        start = ts
        end = ts + pd.Timedelta(minutes=15)
        slice_1m = df.loc[start:end - pd.Timedelta(minutes=1)]
       
        if slice_1m.empty:
            continue
           
        last_1m = slice_1m.iloc[-1]
        entry_price = last_1m['Close']
        sig_ts = last_1m.name # Thời điểm phát tín hiệu là ở thanh 1M cuối cùng
 
        if row['signal_buy']:
            # Tín hiệu Mua
            signals.at[sig_ts, 'signal_side'] = 'BUY'
            signals.at[sig_ts, 'risk_pct'] = base_risk_pct
            signals.at[sig_ts, 'tp_price'] = entry_price * (1 + TP_FACTOR) # TP 4%
            signals.at[sig_ts, 'sl_price'] = entry_price * (1 - SL_FACTOR) # SL 2%
            signals.at[sig_ts, 'note'] = 'M15_RSI_oversold_buy'
           
        elif row['signal_sell']:
            # Tín hiệu Bán
            signals.at[sig_ts, 'signal_side'] = 'SELL'
            signals.at[sig_ts, 'risk_pct'] = base_risk_pct
            signals.at[sig_ts, 'tp_price'] = entry_price * (1 - TP_FACTOR) # TP 4%
            signals.at[sig_ts, 'sl_price'] = entry_price * (1 + SL_FACTOR) # SL 2%
            signals.at[sig_ts, 'note'] = 'M15_RSI_overbought_sell'
           
    return signals
 
def generate_signals1(df_1m: pd.DataFrame,
                     mtf_timeframes: Optional[List[str]] = None,
                     base_risk_pct: float = 0.01) -> pd.DataFrame:
   
    if mtf_timeframes is None:
        mtf_timeframes = ['15T','1H','4H']
 
    df = df_1m.copy()
    df.columns = [c.capitalize() for c in df.columns]
    if 'Close' not in df.columns:
        raise ValueError("generate_signals: df_1m must contain Close column")
 
    # 🚨 BƯỚC SỬA 1: VECTORIZED HÓA RSI 1M TRÊN TOÀN BỘ DỮ LIỆU
    # Tính RSI 1M một lần duy nhất, tránh tính lặp lại trong vòng lặp.
    df['Rsi14_1m'] = talib.RSI(df['Close'].values, timeperiod=14)
    # ------------------------------------------------------------------
 
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
 
    m15 = mtf.get('15T')
    h4 = mtf.get('4H')
 
    if m15 is None:
        return signals
 
    # prepare cross detection on M15
    m15['ema7_prev'] = m15['ema7'].shift(1)
    m15['ema99_prev'] = m15['ema99'].shift(1)
    m15['cross_up'] = (m15['ema7_prev'] <= m15['ema99_prev']) & (m15['ema7'] > m15['ema99'])
    m15['cross_down'] = (m15['ema7_prev'] >= m15['ema99_prev']) & (m15['ema7'] < m15['ema99'])
   
    # Đặt tỷ lệ cố định 4% TP / 2% SL (R:R 2:1)
    TP_FACTOR = 0.04  # 4%
    SL_FACTOR = 0.02  # 2%
 
    # iterate M15 candles where cross happened
    for ts, row in m15.iterrows():
        if not (row.get('cross_up', False) or row.get('cross_down', False)):
            continue
 
        # find H4 trend at this timestamp
        trend_is_bull = None
        try:
            h4_slice = h4.loc[:ts]
            if not h4_slice.empty:
                last_h4 = h4_slice.iloc[-1]
                trend_is_bull = (last_h4['ema7'] > last_h4['ema99'])
        except Exception:
            trend_is_bull = None
 
        # map M15 candle to 1m bars
        start = ts
        end = ts + pd.Timedelta(minutes=15)
        slice_1m = df.loc[start:end - pd.Timedelta(minutes=1)]
        if slice_1m.empty:
            continue
           
        last_1m = slice_1m.iloc[-1]
 
        # 🚨 BƯỚC SỬA 2: LOẠI BỎ TÍNH TOÁN LẶP LẠI VÀ THAY BẰNG TRA CỨU
        rsi_1m = last_1m['Rsi14_1m']
       
        if np.isnan(rsi_1m):
            continue
        # ------------------------------------------------------------------
 
        # Build signal
        entry_price = last_1m['Close']
 
        if row['cross_up'] and (trend_is_bull is None or trend_is_bull) and rsi_1m <= 50:
            # BUY signal (Long Entry)
            sig_ts = last_1m.name
            signals.at[sig_ts, 'signal_side'] = 'BUY'
            signals.at[sig_ts, 'risk_pct'] = base_risk_pct
           
            # CẬP NHẬT TP/SL CHO LONG: (4% TP, 2% SL)
            signals.at[sig_ts, 'tp_price'] = entry_price * (1 + TP_FACTOR)
            signals.at[sig_ts, 'sl_price'] = entry_price * (1 - SL_FACTOR)
           
            signals.at[sig_ts, 'note'] = 'm15_cross_up_confirmed_by_1m_rsi'
           
        elif row['cross_down'] and (trend_is_bull is None or not trend_is_bull) and rsi_1m >= 50:
            # SELL signal (Short Entry)
            sig_ts = last_1m.name
            signals.at[sig_ts, 'signal_side'] = 'SELL'
            signals.at[sig_ts, 'risk_pct'] = base_risk_pct
           
            # CẬP NHẬT TP/SL CHO SHORT: (4% TP, 2% SL)
            signals.at[sig_ts, 'tp_price'] = entry_price * (1 - TP_FACTOR)
            signals.at[sig_ts, 'sl_price'] = entry_price * (1 + SL_FACTOR)
           
            signals.at[sig_ts, 'note'] = 'm15_cross_down_confirmed_by_1m_rsi'
 
    return signals