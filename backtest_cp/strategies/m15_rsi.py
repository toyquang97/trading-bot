# strategies/active.py
import pandas as pd
import numpy as np
from typing import List, Optional
# from common import *
from strategies.common import *
import talib
# strategies/m15_rsi.py


file_path = 'BTCUSDT_15m_20251001_0000_to_20251127_2359.csv'
 

def generate(df_base: pd.DataFrame,
             base_risk_pct: float = 0.01) -> pd.DataFrame:


    df_15m_raw = pd.read_csv(file_path)

    df_15m = clean_ohlc(df_15m_raw, timeframe='15min')

    # -------------------------------
    # FIX LỖI INDEX LÀ INT
    df_base1 = df_base.copy()
    df_mtf = df_15m.copy()

    close = df_mtf['close'].values
    df_mtf['rsi14'] = talib.RSI(close, timeperiod=14)
    df_mtf['rsi14_prev'] = df_mtf['rsi14'].shift(1)

    df_mtf['signal_buy'] = (df_mtf['rsi14_prev'] >= 15) & (df_mtf['rsi14'] < 15)
    df_mtf['signal_sell'] = (df_mtf['rsi14_prev'] <= 80) & (df_mtf['rsi14'] > 80)

    signals = pd.DataFrame(index=df_base1.index)
    signals['signal_side'] = None
    signals['note'] = None
    signals['size'] = np.nan
    signals['risk_pct'] = np.nan
    signals['tp_price'] = np.nan
    signals['sl_price'] = np.nan

    TP_FACTOR = 0.04
    SL_FACTOR = 0.02

    for ts, row in df_mtf.iterrows():
        if not (row['signal_buy'] or row['signal_sell']):
            continue

        block_start = ts
        block_end = ts + pd.Timedelta(minutes=15)
        slice_1m = df_base.loc[block_start:block_end - pd.Timedelta(minutes=1)]

        if slice_1m.empty:
            continue

        last_candle = slice_1m.iloc[-1]
        entry_price = last_candle['close']
        entry_ts = last_candle.name

        if row['signal_buy']:
            signals.at[entry_ts, 'signal_side'] = 'BUY'
            signals.at[entry_ts, 'tp_price'] = entry_price * (1 + TP_FACTOR)
            signals.at[entry_ts, 'sl_price'] = entry_price * (1 - SL_FACTOR)

        elif row['signal_sell']:
            signals.at[entry_ts, 'signal_side'] = 'SELL'
            signals.at[entry_ts, 'tp_price'] = entry_price * (1 - TP_FACTOR)
            signals.at[entry_ts, 'sl_price'] = entry_price * (1 + SL_FACTOR)

        signals.at[entry_ts, 'risk_pct'] = base_risk_pct
        signals = signals[signals['signal_side'].notna()]
        signals.to_csv('debug_m15_rsi_signals.csv')
    return signals

