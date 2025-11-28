# backtest_binance.py
import time
import math
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# try to import TA helper lib (optional)
try:
    import ta
    _HAS_TA = True
except Exception:
    _HAS_TA = False

# python-binance client
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

# ---------- Config ----------
API_KEY = None        # nếu có thì điền, nếu để None vẫn có thể fetch  -- tuy nhiên rate-limit chặt hơn
API_SECRET = None
SYMBOL = "BTCUSDT"
START_STR = "2023-01-01 00:00:00"
END_STR = None        # None để lấy tới hiện tại
BINANCE_INTERVAL = "15m"  # we'll fetch at 15m base, then resample
START_BALANCE = 1000.0
FEE_RATE = 0.00075
SLIPPAGE_PCT = 0.0005

# helper to map binance interval to pandas offset if needed
BINANCE_TO_PANDAS = {
    "1m": "1T", "3m": "3T", "5m": "5T", "15m": "15T", "30m": "30T",
    "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "8h": "8H",
    "12h": "12H", "1d": "1D", "3d": "3D", "1w": "1W", "1M": "1M"
}

# ---------- Fetch klines with python-binance ----------
def fetch_klines_binance(symbol: str, interval: str = "15m", start_str: str = None, end_str: str = None, limit: int = 1000):
    """
    Return DataFrame with columns: timestamp (ms), open, high, low, close, volume
    Uses client.get_historical_klines and handles pagination (since Binance returns max 1000 bars per call).
    start_str: string like "2023-01-01 00:00:00" or None (for earliest)
    end_str: string or None
    """
    client = Client(API_KEY, API_SECRET) if API_KEY else Client()
    all_rows = []
    fetch_start = start_str
    while True:
        try:
            klines = client.get_historical_klines(symbol, interval, fetch_start, end_str, limit=limit)
        except (BinanceAPIException, BinanceRequestException) as e:
            print("Binance API error:", e)
            print("Thử chờ 1s và retry...")
            time.sleep(1)
            continue
        if not klines:
            break
        all_rows.extend(klines)
        # last kline close time (ms)
        last_open_time = klines[-1][0]
        # advance 1 ms after last to avoid duplication
        fetch_start = str(pd.to_datetime(last_open_time, unit='ms') + pd.Timedelta(milliseconds=1))
        # if fewer than limit returned -> finished
        if len(klines) < limit:
            break
        # safety sleep to respect rate limit
        time.sleep(0.3)
    if not all_rows:
        raise ValueError("No klines fetched. Check symbol/interval/start")
    # parse into DataFrame
    df = pd.DataFrame(all_rows, columns=[
        "open_time","open","high","low","close","volume","close_time","qav","num_trades",
        "taker_base_vol","taker_quote_vol","ignore"
    ])
    # convert types
    df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
    for c in ['open','high','low','close','volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df[['timestamp','open','high','low','close','volume']].set_index('timestamp')
    df = df.sort_index()
    return df

# ---------- resample function (same as before) ----------
def resample_ohlcv(df, rule):
    o = df['open'].resample(rule).first()
    h = df['high'].resample(rule).max()
    l = df['low'].resample(rule).min()
    c = df['close'].resample(rule).last()
    v = df['volume'].resample(rule).sum()
    res = pd.DataFrame({'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})
    res = res.dropna()
    return res

# ---------- indicators / signals (reuse your logic) ----------
def add_indicators(df):
    df['ema7'] = df['close'].ewm(span=7, adjust=False).mean()
    df['ema99'] = df['close'].ewm(span=99, adjust=False).mean()
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['roc_10'] = df['close'].pct_change(10)
    return df

def detect_trend(main_tf_df):
    main = main_tf_df.copy()
    main['trend_main'] = 'sideway'
    main.loc[main['roc_10'] > 0.02, 'trend_main'] = 'up'
    main.loc[main['roc_10'] < -0.02, 'trend_main'] = 'down'
    return main['trend_main']

def generate_signals(m15_df, main_trend_series):
    df = m15_df.copy()
    df['ema_cross_up'] = (df['ema7'] > df['ema99']) & (df['ema7'].shift(1) <= df['ema99'].shift(1))
    df['ema_cross_dn'] = (df['ema7'] < df['ema99']) & (df['ema7'].shift(1) >= df['ema99'].shift(1))
    df = df.merge(main_trend_series.rename('trend_main'), how='left', left_index=True, right_index=True)
    df['trend_main'] = df['trend_main'].fillna(method='ffill')
    df['signal'] = 0
    df.loc[(df['trend_main'] == 'up') & (df['ema_cross_up']), 'signal'] = 1
    return df

# ---------- BacktestEngine: reuse earlier engine (copy/paste) ----------
class BacktestEngine:
    def __init__(self, data, start_balance=1000.0, fee_rate=0.00075, slippage=0.0005):
        self.data = data.copy()
        self.start_balance = start_balance
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.equity = start_balance
        self.cash = start_balance
        self.position = 0.0
        self.entry_price = None
        self.trades = []
        self.equity_curve = []

    def _apply_fee_and_slippage(self, price, size, side):
        slippage = price * self.slippage
        price_effective = price + slippage if side=='buy' else price - slippage
        fee = price_effective * abs(size) * self.fee_rate
        return price_effective, fee

    def _record_equity(self, timestamp, price):
        asset_value = self.position * price
        total = self.cash + asset_value
        self.equity_curve.append({'timestamp': timestamp, 'equity': total})
        self.equity = total

    def run(self):
        for idx, row in self.data.iterrows():
            price = row['close']
            self._record_equity(idx, price)

            if row['signal'] == 1 and self.position == 0:
                usd_to_use = max(self.equity * 0.1, 10.0)
                size = usd_to_use / row['open']
                price_eff, fee = self._apply_fee_and_slippage(row['open'], size, 'buy')
                cost = price_eff * size + fee
                if cost <= self.cash:
                    self.cash -= cost
                    self.position += size
                    self.entry_price = price_eff
                    self.trades.append({'timestamp': idx, 'side': 'buy', 'price': price_eff, 'size': size, 'fee': fee})
            if self.position > 0:
                TP_PCT = 0.01
                stop_price = self.entry_price * (1 + TP_PCT)
                if row['high'] >= stop_price:
                    sell_price_eff, fee = self._apply_fee_and_slippage(stop_price, self.position, 'sell')
                    proceeds = sell_price_eff * self.position - fee
                    self.cash += proceeds
                    self.trades.append({'timestamp': idx, 'side': 'sell', 'price': sell_price_eff, 'size': -self.position, 'fee': fee})
                    self.position = 0.0
                    self.entry_price = None
        self._record_equity(self.data.index[-1], self.data['close'].iloc[-1])

    def results(self):
        df_eq = pd.DataFrame(self.equity_curve).set_index('timestamp')
        df_eq['returns'] = df_eq['equity'].pct_change().fillna(0)
        total_return = (df_eq['equity'].iloc[-1] / df_eq['equity'].iloc[0]) - 1
        days = (df_eq.index[-1] - df_eq.index[0]).total_seconds() / (3600*24)
        cagr = (df_eq['equity'].iloc[-1] / df_eq['equity'].iloc[0]) ** (365.0/days) - 1 if days>0 else 0.0
        cummax = df_eq['equity'].cummax()
        drawdown = (df_eq['equity'] - cummax) / cummax
        max_dd = drawdown.min()
        if df_eq['returns'].std() > 0:
            sharpe = (df_eq['returns'].mean() / df_eq['returns'].std()) * math.sqrt(252)
        else:
            sharpe = np.nan
        return {'equity_curve': df_eq, 'total_return': total_return, 'cagr': cagr, 'max_drawdown': max_dd, 'sharpe': sharpe, 'n_trades': len([t for t in self.trades if t['side']=='buy'])}

# ---------- Main ----------
def main():
    print("Fetching data from Binance:", SYMBOL, BINANCE_INTERVAL, "from", START_STR)
    df_15m = fetch_klines_binance(SYMBOL, BINANCE_INTERVAL, START_STR, END_STR)
    print("Downloaded bars:", len(df_15m))

    # build higher TFs
    tf_m15 = resample_ohlcv(df_15m, "15T")
    tf_h1 = resample_ohlcv(df_15m, "1H")
    tf_h4 = resample_ohlcv(df_15m, "4H")
    tf_1d = resample_ohlcv(df_15m, "1D")

    tf_m15 = add_indicators(tf_m15)
    tf_h1 = add_indicators(tf_h1)
    tf_h4 = add_indicators(tf_h4)
    tf_1d = add_indicators(tf_1d)

    trend_main = detect_trend(tf_1d)
    trend_on_m15 = trend_main.reindex(tf_m15.index, method='ffill')

    signals = generate_signals(tf_m15, trend_on_m15)
    tf_m15 = tf_m15.merge(signals[['signal']], left_index=True, right_index=True, how='left')
    tf_m15['signal'] = tf_m15['signal'].fillna(0)

    engine = BacktestEngine(tf_m15, start_balance=START_BALANCE, fee_rate=FEE_RATE, slippage=SLIPPAGE_PCT)
    engine.run()
    res = engine.results()

    print("Trades:", engine.trades)
    print("Total return: {:.2%}".format(res['total_return']))
    print("CAGR: {:.2%}".format(res['cagr']))
    print("Max drawdown: {:.2%}".format(res['max_drawdown']))
    print("Sharpe:", res['sharpe'])
    print("Number of trades:", res['n_trades'])

    plt.figure(figsize=(10,5))
    res['equity_curve']['equity'].plot(title='Equity Curve')
    plt.show()

if __name__ == "__main__":
    main()
