# force_signal_test.py
import pandas as pd
import numpy as np
from engine import BacktestEngine
from evaluation import calculate_performance_metrics

path = 'BTCUSDT_1m_20250101_0000_to_20250301_2359.csv'
df = pd.read_csv(path)
if 'Time' in df.columns:
    df['Time'] = pd.to_datetime(df['Time']); df = df.set_index('Time')
elif 'open_time' in df.columns:
    df['open_time'] = pd.to_datetime(df['open_time']); df = df.set_index('open_time')
else:
    df.iloc[:,0] = pd.to_datetime(df.iloc[:,0]); df = df.set_index(df.columns[0])
df.columns = [c.capitalize() for c in df.columns]

# create empty signals df with same index
signals = pd.DataFrame(index=df.index)
signals['signal_side'] = pd.Series(index=df.index, dtype=object)
signals['size'] = np.nan
signals['risk_pct'] = np.nan
signals['tp_price'] = np.nan
signals['sl_price'] = np.nan

# choose timestamp to submit a BUY
ts = df.index[1000]   # change index as you like
signals.at[ts, 'signal_side'] = 'BUY'
signals.at[ts, 'size'] = 1.0
signals.at[ts, 'tp_price'] = df.at[ts, 'Close'] * 1.01
signals.at[ts, 'sl_price'] = df.at[ts, 'Close'] * 0.995

print("Forcing signal at", ts, "price:", df.at[ts,'Close'])

engine = BacktestEngine(initial_capital=100000.0, fee_rate=0.00075, slippage_pct=0.0005)
output_data, trades_df = engine.run_backtest(df, signals_df=signals, prefer_risk_pct=False)
print("Trades len:", len(trades_df))
print(trades_df.head())
# show equity tail
print(output_data['equity'].dropna().tail(10))
