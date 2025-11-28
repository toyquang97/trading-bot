from include import *

#============================================================#
#  LOAD CSV (CHỈ SỬA ĐƯỜNG DẪN NÀY)
#============================================================#
# csv_path = "BTCUSDT_4h_20251101_to_20251120.csv"
csv_path = os.path.join(os.path.dirname(__file__), "data", "BTCUSDT_4h_20251101_to_20251120.csv")
# ---------- Load & normalise ----------
df = pd.read_csv(csv_path)
# detect datetime column
datetime_col = None
for c in df.columns:
    if "time" in c.lower() or "date" in c.lower() or "timestamp" in c.lower():
        datetime_col = c
        break
if datetime_col is None:
    datetime_col = df.columns[0]

df[datetime_col] = pd.to_datetime(df[datetime_col])
df = df.sort_values(by=datetime_col).reset_index(drop=True)
df.set_index(datetime_col, inplace=True)

# normalize column names to lower-case common names
colmap = {}
for c in df.columns:
    cl = c.lower()
    if cl == "open": colmap[c] = "open"
    if cl == "high": colmap[c] = "high"
    if cl == "low":  colmap[c] = "low"
    if cl == "close":colmap[c] = "close"
    if cl == "volume":colmap[c] = "volume"
df = df.rename(columns=colmap)

# ensure numeric
for k in ("open","high","low","close"):
    if k not in df.columns:
        raise RuntimeError(f"Missing column {k} in CSV")
    df[k] = pd.to_numeric(df[k], errors="coerce")

# create numpy arrays once (safe, no pandas position warning)
close = df["close"].values
high  = df["high"].values
low   = df["low"].values
dates = df.index

# ---------- 1) ZigZag pivot detector (uses numpy arrays) ----------
def zigzag_pivots_np(high_np, low_np, close_np, pct=3.0):
    n = len(high_np)
    pivots = np.zeros(n, dtype=int)
    # keep last pivot price and type as numpy scalars
    last_price = close_np[0]
    last_idx = 0
    trend = None

    for i in range(1, n):
        # use numpy indexing (no pandas Series)
        up = (high_np[i] - last_price) / last_price * 100.0
        down = (last_price - low_np[i]) / last_price * 100.0

        if trend is None:
            if up > pct:
                pivots[i] = 1
                trend = "up"
                last_idx = i
                last_price = high_np[i]
            elif down > pct:
                pivots[i] = -1
                trend = "down"
                last_idx = i
                last_price = low_np[i]
        elif trend == "up":
            if high_np[i] > last_price:
                # extend pivot high
                pivots[last_idx] = 0
                pivots[i] = 1
                last_idx = i
                last_price = high_np[i]
            elif down > pct:
                pivots[i] = -1
                trend = "down"
                last_idx = i
                last_price = low_np[i]
        else:  # trend == "down"
            if low_np[i] < last_price:
                pivots[last_idx] = 0
                pivots[i] = -1
                last_idx = i
                last_price = low_np[i]
            elif up > pct:
                pivots[i] = 1
                trend = "up"
                last_idx = i
                last_price = high_np[i]
    return pivots

df["pivot"] = zigzag_pivots_np(high, low, close, pct=3.0)

# build segments by using df.iloc for positions -> safe
def build_segments_from_pivots(df, pivot_col="pivot"):
    segs = []
    piv = df[pivot_col].to_numpy()
    idxs = np.where(piv != 0)[0]
    for a_idx, b_idx in zip(idxs[:-1], idxs[1:]):
        if piv[a_idx] == piv[b_idx]:
            if piv[a_idx] == 1:
                y0 = df["high"].to_numpy()[a_idx]
                y1 = df["high"].to_numpy()[b_idx]
            else:
                y0 = df["low"].to_numpy()[a_idx]
                y1 = df["low"].to_numpy()[b_idx]
            segs.append((df.index[a_idx], y0, df.index[b_idx], y1))
    return segs

zigzag_segments = build_segments_from_pivots(df, "pivot")

# ---------- 2) Regression trendline (use numpy, return datetimes slice) ----------
def regression_trend(df, window=100):
    if window > len(df):
        window = len(df)
    y = df["close"].to_numpy()[-window:]
    x = np.arange(len(y))
    m, b = np.polyfit(x, y, 1)
    y_pred = m * x + b
    x_idx = df.index[-window:]
    return x_idx, y_pred, m, b

reg_idx, reg_y, slope, intercept = regression_trend(df, window=100)

# ---------- 3) Peaks/Valleys (scipy if available; fallback local method) ----------
def find_peaks_valleys(series_np, distance=5):
    try:
        from scipy.signal import find_peaks
        peaks, _ = find_peaks(series_np, distance=distance)
        valleys, _ = find_peaks(-series_np, distance=distance)
        return peaks, valleys
    except Exception:
        # fallback: local maxima/minima in sliding window
        n = len(series_np)
        peaks = []
        valleys = []
        w = distance
        for i in range(w, n-w):
            window = series_np[i-w:i+w+1]
            if series_np[i] == np.max(window) and np.sum(window == np.max(window)) == 1:
                peaks.append(i)
            if series_np[i] == np.min(window) and np.sum(window == np.min(window)) == 1:
                valleys.append(i)
        return np.array(peaks), np.array(valleys)

peaks_idx, valleys_idx = find_peaks_valleys(close, distance=5)

# ---------- Plot with Plotly ----------
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=dates, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="OHLC"
))

# pivots markers
pivots_mask = df["pivot"] != 0
if pivots_mask.any():
    piv_df = df.loc[pivots_mask]
    yvals = np.where(piv_df["pivot"].to_numpy() == 1, piv_df["high"].to_numpy(), piv_df["low"].to_numpy())
    fig.add_trace(go.Scatter(x=piv_df.index, y=yvals, mode="markers", marker=dict(symbol="x", size=9), name="Pivots"))

# zigzag segments
for (x0,y0,x1,y1) in zigzag_segments:
    fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", line=dict(width=2, dash="dot"), name="ZZ-line"))

# regression
fig.add_trace(go.Scatter(x=reg_idx, y=reg_y, mode="lines", line=dict(width=3), name=f"Regr slope={slope:.6f}"))

# peaks/valleys
if len(peaks_idx)>0:
    fig.add_trace(go.Scatter(x=df.index[peaks_idx], y=close[peaks_idx], mode="markers", marker=dict(symbol="triangle-up", size=8), name="Peaks"))
if len(valleys_idx)>0:
    fig.add_trace(go.Scatter(x=df.index[valleys_idx], y=close[valleys_idx], mode="markers", marker=dict(symbol="triangle-down", size=8), name="Valleys"))

fig.update_layout(title="Trend detection (fixed indexing - no FutureWarning)", xaxis_rangeslider_visible=False, height=800)
fig.show()