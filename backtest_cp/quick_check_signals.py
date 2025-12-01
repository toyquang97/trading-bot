# quick_check_signals.py (run in project dir)
import pandas as pd
from strategy import generate_signals
import numpy as np

# load 1m file (cái file m upload)
path = 'BTCUSDT_1m_20251001_0000_to_20251127_2359.csv'
df = pd.read_csv(path)
# try to set index column: detect Time/open_time or first col
if 'Time' in df.columns:
    df['Time'] = pd.to_datetime(df['Time'])
    df = df.set_index('Time')
elif 'open_time' in df.columns:
    df['open_time'] = pd.to_datetime(df['open_time'])
    df = df.set_index('open_time')
else:
    # assume first col is timestamp
    df.iloc[:,0] = pd.to_datetime(df.iloc[:,0])
    df = df.set_index(df.columns[0])

# normalize colnames to be safe
df.columns = [c.capitalize() for c in df.columns]

signals = generate_signals(df, base_risk_pct=0.01)
print("Total signals (non-null signal_side):", signals['signal_side'].count())
print("Signals timestamps and rows:")
print(signals[signals['signal_side'].notna()].head(20))
# inspect a bit more
print("Signals dtypes:\n", signals.dtypes)
