# fast-trending.py
from include import *   

csv_path = os.path.join(os.path.dirname(__file__), "data", "BTCUSDT_4h_20251101_0000_to_20251120_2359.csv")
# ---------- Load & normalise ----------


out_html = "trend_find_peaks.html"

# Parameters
min_distance = max(1, int(0.005 * 1000))  # example (will be adapted below)
prominence = None  # set a float for stronger peaks e.g., 200.0

# Load
df = pd.read_csv(csv_path)
dt = next((c for c in df.columns if "time" in c.lower() or "date" in c.lower()), df.columns[0])
df[dt] = pd.to_datetime(df[dt])
df = df.sort_values(dt).reset_index(drop=True).set_index(dt)
for k in ("open","high","low","close"):
    df[k] = pd.to_numeric(df[k], errors="coerce")
high = df["high"].to_numpy(); low = df["low"].to_numpy(); close = df["close"].to_numpy()
dates = df.index.to_numpy()
n = len(df)

# tune min_distance relative to length
min_distance = max(1, int(n * 0.01))  # e.g., 1% of bars

peaks_idx, _ = find_peaks(high, distance=min_distance, prominence=prominence)
valleys_idx, _ = find_peaks(-low, distance=min_distance, prominence=prominence)

# merge and alternate
pairs = sorted([(i, 1) for i in peaks_idx] + [(i, -1) for i in valleys_idx], key=lambda x: x[0])
# compress same-type neighbors by keeping the more extreme (peak: higher high, valley: lower low)
clean = []
for idx, typ in pairs:
    if not clean:
        clean.append((idx, typ))
    else:
        if typ == clean[-1][1]:
            prev_idx, prev_typ = clean[-1]
            if typ == 1:
                # keep the higher high
                if high[idx] >= high[prev_idx]:
                    clean[-1] = (idx, typ)
            else:
                if low[idx] <= low[prev_idx]:
                    clean[-1] = (idx, typ)
        else:
            clean.append((idx, typ))

# build segments (connect alternating)
segments = []
for (a, ta), (b, tb) in zip(clean[:-1], clean[1:]):
    ya = high[a] if ta==1 else low[a]
    yb = high[b] if tb==1 else low[b]
    segments.append((dates[a], ya, dates[b], yb))

# Plot
fig = go.Figure()
fig.add_trace(go.Scatter(x=dates, y=close, mode="lines", line=dict(color="black", width=1), name="price"))
for (x0,y0,x1,y1) in segments:
    fig.add_trace(go.Scatter(x=[x0,x1], y=[y0,y1], mode="lines", line=dict(color="red", width=4), name="trendline"))
fig.update_layout(title=f"find_peaks (dist={min_distance}) trendline only", xaxis_rangeslider_visible=False, width=1000, height=500)
fig.write_html(out_html)
print("Saved:", os.path.abspath(out_html))