import pandas as pd
import numpy as np
import talib
from typing import List, Optional
# from common import *
from strategies.common import *


file_path = get_data_path("BTCUSDT_15m_20251001_0000_to_20251127_2359.csv")
# file_path = 'BTCUSDT_15m_20251001_0000_to_20251127_2359.csv'
# file_4h_path = "data\BTCUSDT_4h_20251001_0000_to_20251127_2359.csv"

def generate(df_base: pd.DataFrame,
             base_risk_pct: float = 0.01) -> pd.DataFrame:
    """
    Strategy: Bollinger Bands (20,2) on 15m + Volume spike confirmation.
    - Buy when 15m close < lower_band AND 15m volume > avg_volume_20 * VOL_MULT
    - Sell when 15m close > upper_band AND 15m volume > avg_volume_20 * VOL_MULT
    - Entry price taken as last 1m close inside that 15m block
    - TP/SL factors same as trước (TP 4%, SL 2%)
    - Returns signals DataFrame containing only actual signals (no full-index)
    """

    # --- CONFIG (tweak these if cần)
    BB_PERIOD = 20
    BB_STD = 2
    VOL_PERIOD = 20
    VOL_MULT = 1.5   # volume phải lớn hơn trung bình * VOL_MULT để coi là spike
    TP_FACTOR = 0.04
    SL_FACTOR = 0.02

    # --- read precomputed 15m CSV (keeps same pattern như hàm cũ)
    # NOTE: `file_path` must exist in the calling scope (same as hàm cũ)
    df_15m_raw = pd.read_csv(file_path)
    # Normalize/clean 15m using the same helper (expect clean_ohlc exists)
    df_15m = clean_ohlc(df_15m_raw, timeframe='15min')

    # --- COPY & normalize incoming 1m base
    if df_base is None:
        raise ValueError("generate: df_base must not be None")

    df_base = df_base.copy()
    # ensure index is datetime
    try:
        if not isinstance(df_base.index, pd.DatetimeIndex):
            # if there's a column named open_time use it, otherwise try to convert index
            if 'open_time' in df_base.columns:
                df_base['open_time'] = pd.to_datetime(df_base['open_time'], errors='coerce')
                df_base = df_base.dropna(subset=['open_time'])
                df_base = df_base.set_index('open_time')
            else:
                df_base.index = pd.to_datetime(df_base.index)
    except Exception:
        df_base.index = pd.to_datetime(df_base.index)

    # floor index to 1min and sort
    df_base = df_base.sort_index()
    df_base.index = df_base.index.floor('1min')

    # normalize column names to lowercase for safe access
    df_base.columns = [c.lower() for c in df_base.columns]

    # same normalization for 15m df
    df_15m = df_15m.copy()
    if not isinstance(df_15m.index, pd.DatetimeIndex):
        if 'open_time' in df_15m.columns:
            df_15m['open_time'] = pd.to_datetime(df_15m['open_time'], errors='coerce')
            df_15m = df_15m.dropna(subset=['open_time']).set_index('open_time')
        else:
            df_15m.index = pd.to_datetime(df_15m.index)
    df_15m = df_15m.sort_index()
    df_15m.index = df_15m.index.floor('15min')
    df_15m.columns = [c.lower() for c in df_15m.columns]

    # --- Compute Bollinger Bands & volume avg on 15m
    close_15 = df_15m['close'].values
    upper, mid, lower = talib.BBANDS(close_15, timeperiod=BB_PERIOD, nbdevup=BB_STD, nbdevdn=BB_STD)
    df_15m['bb_upper'] = upper
    df_15m['bb_mid'] = mid
    df_15m['bb_lower'] = lower

    # Volume moving average
    if 'volume' in df_15m.columns:
        df_15m['vol_ma'] = df_15m['volume'].rolling(VOL_PERIOD, min_periods=1).mean()
    else:
        # If no volume in 15m, try to aggregate from 1m
        if 'volume' in df_base.columns:
            # aggregate 1m -> 15m sum volume aligned by floor
            vol_15_from_1m = df_base['volume'].resample('15min').sum()
            df_15m = df_15m.join(vol_15_from_1m.rename('volume'), how='left')
            df_15m['vol_ma'] = df_15m['volume'].rolling(VOL_PERIOD, min_periods=1).mean()
        else:
            df_15m['volume'] = np.nan
            df_15m['vol_ma'] = np.nan

    # signals columns on 15m
    df_15m['vol_spike'] = df_15m['volume'] > (df_15m['vol_ma'] * VOL_MULT)
    df_15m['bb_oversold'] = df_15m['close'] < df_15m['bb_lower']
    df_15m['bb_overbought'] = df_15m['close'] > df_15m['bb_upper']

    df_15m['signal_buy'] = df_15m['bb_oversold'] & df_15m['vol_spike']
    df_15m['signal_sell'] = df_15m['bb_overbought'] & df_15m['vol_spike']

    # --- prepare signals DataFrame indexed by 1m times (we will only keep rows with signals)
    signals = pd.DataFrame(columns=['signal_side','note','size','risk_pct','tp_price','sl_price'])
    # We'll populate rows by timestamp (entry_ts) as index

    # --- iterate over 15m candles that have signal
    for ts, row in df_15m.iterrows():
        if not (row.get('signal_buy', False) or row.get('signal_sell', False)):
            continue

        block_start = ts
        block_end = ts + pd.Timedelta(minutes=15)
        # select 1m candles inside the 15m block (inclusive start, inclusive end -1min)
        slice_1m = df_base.loc[block_start : block_end - pd.Timedelta(minutes=1)]

        if slice_1m.empty:
            # no 1m data for this block -> skip
            continue

        # Optional: additional confirmation using 1m volume spike inside the block
        vol1m = None
        if 'volume' in df_base.columns:
            # compare last 1m volume to its rolling mean (e.g., last 60 1m candles approx 1h)
            last_vol = slice_1m['volume'].iloc[-1]
            vol_ma_1h = df_base['volume'].rolling(60, min_periods=1).mean().iloc[-1]
            vol1m = last_vol > (vol_ma_1h * VOL_MULT)
            # require at least either 15m vol spike or 1m vol spike (we already had 15m vol_spike)
            # Here we don't require extra — but you can uncomment below to require both:
            # if not vol1m:
            #     continue

        last_candle = slice_1m.iloc[-1]
        entry_price = last_candle['close']
        entry_ts = last_candle.name

        if row['signal_buy']:
            sig_side = 'BUY'
            note = 'M15_BB_vol_buy'
            tp = entry_price * (1 + TP_FACTOR)
            sl = entry_price * (1 - SL_FACTOR)
        else:
            sig_side = 'SELL'
            note = 'M15_BB_vol_sell'
            tp = entry_price * (1 - TP_FACTOR)
            sl = entry_price * (1 + SL_FACTOR)

        # append into signals (index = entry timestamp)
        signals.loc[entry_ts] = {
            'signal_side': sig_side,
            'note': note,
            'size': np.nan,
            'risk_pct': base_risk_pct,
            'tp_price': tp,
            'sl_price': sl
        }

    # only keep rows with signals (already only appended signals) and sort by time
    if not signals.empty:
        signals.index.name = 'timestamp'
        signals = signals.sort_index()

            # Tên folder lưu file
    out_dir = "strategies/debug_output"
        # Tạo folder nếu chưa có
    os.makedirs(out_dir, exist_ok=True)
    signals.to_csv(f"{out_dir}/debug_boll_vol_signals.csv")
    return signals