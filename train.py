# pip install python-binance pandas numpy scikit-learn torch

import numpy as np
import pandas as pd
from binance.client import Client
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
import torch
from torch.utils.data import Dataset, DataLoader, Subset
import torch.nn as nn
import torch.optim as optim
from load_env import *

# --- 1) get OHLCV from Binance (python-binance)
# api_key = "YOUR_KEY"
# api_secret = "YOUR_SECRET"
# client = Client(api_key, api_secret)

def fetch_klines(symbol="BTCUSDT", interval="1h", limit=1000):
    rows = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(rows, columns=[
        "open_time","open","high","low","close","volume","close_time","qav","num_trades",
        "taker_base","taker_quote","ignore"
    ])
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)
    df = df.set_index('open_time')
    return df

df = fetch_klines("BTCUSDT","1h",limit=2000)
print(df.head())
# --- 2) simple features & label (next bar direction)
df['ret'] = df['close'].pct_change()
df['ma10'] = df['close'].rolling(10).mean()
df['ma50'] = df['close'].rolling(50).mean()
df['rsi'] = (100 - (100/(1 + df['ret'].rolling(14).apply(lambda x: (x[x>0].sum()/len(x)) / (abs(x[x<0].sum()/len(x))+1e-8)))))
# fallback if rsi calculation invalid:
df['rsi'] = df['rsi'].fillna(50)

df = df.dropna()

# label: 1 if next bar up else 0
df['future_ret'] = df['close'].shift(-1) / df['close'] - 1
df = df.dropna()
df['label'] = (df['future_ret'] > 0).astype(int)

features = ['ret','ma10','ma50','rsi','volume']
X = df[features].values
y = df['label'].values

