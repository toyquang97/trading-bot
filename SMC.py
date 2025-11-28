# smc_simple.py
from include import *

# --- config: đổi đường dẫn CSV của mày ở đây ---
# csv_path = "BTCUSDT_4h_20251101_to_20251120.csv"  # <-- đổi nếu cần
csv_path = os.path.join(os.path.dirname(__file__), "data", "BTCUSDT_4h_20251101_0000_to_20251120_2359.csv")
out_html = "smc_tradingview_output.html"

# ==== LOAD DATA ====
df = pd.read_csv(csv_path)
dtcol = next((c for c in df.columns if "time" in c.lower() or "date" in c.lower()), df.columns[0])
df[dtcol] = pd.to_datetime(df[dtcol], utc=True).dt.tz_convert(None)

df = df.sort_values(dtcol).reset_index(drop=True)
df.set_index(dtcol, inplace=True)

for c in ("open", "high", "low", "close"):
    df[c] = pd.to_numeric(df[c], errors="coerce")

high = df["high"].to_numpy()
low  = df["low"].to_numpy()
close = df["close"].to_numpy()
dates = df.index.to_numpy()
n = len(df)

# ======================================================================
# 1) SWING HIGH / SWING LOW DETECTION (TradingView style: 2-left, 2-right)
# ======================================================================
def detect_swing(df, left=2, right=2):
    highs = df["high"].values
    lows  = df["low"].values
    n = len(df)

    swing_high = np.zeros(n, dtype=bool)
    swing_low  = np.zeros(n, dtype=bool)

    for i in range(left, n-right):
        if highs[i] == max(highs[i-left:i+right+1]):
            if np.sum(highs[i-left:i+right+1] == highs[i]) == 1:
                swing_high[i] = True

        if lows[i] == min(lows[i-left:i+right+1]):
            if np.sum(lows[i-left:i+right+1] == lows[i]) == 1:
                swing_low[i] = True

    return swing_high, swing_low

sw_high, sw_low = detect_swing(df)

# ======================================================================
# 2) BREAK OF STRUCTURE (BOS) + CHoCH
# ======================================================================
structure = []   # list of dicts: {"idx": i, "type": "BOS_up"/"BOS_down"/"CHoCH_up"/"CHoCH_down"}

last_peak = None
last_valley = None
trend = None   # "up" or "down"

for i in range(n):
    if sw_high[i]:
        if last_peak is not None:
            # new HH -> BOS up if breaking last high
            if high[i] > high[last_peak]:
                structure.append({"idx": i, "type": "BOS_up"})
                trend = "up"
            else:
                structure.append({"idx": i, "type": "CHoCH_down"})
        last_peak = i

    if sw_low[i]:
        if last_valley is not None:
            # new LL -> BOS down
            if low[i] < low[last_valley]:
                structure.append({"idx": i, "type": "BOS_down"})
                trend = "down"
            else:
                structure.append({"idx": i, "type": "CHoCH_up"})
        last_valley = i

# ======================================================================
# 3) ORDER BLOCK DETECTION (ICT LOGIC)
#    - Bullish OB = last bearish candle before BOS_up
#    - Bearish OB = last bullish candle before BOS_down
# ======================================================================
order_blocks = []

for s in structure:
    idx = s["idx"]
    t = s["type"]

    # ---- Bullish OB ----
    if t == "BOS_up":
        j = idx-1
        while j >= 0 and df["close"].iloc[j] >= df["open"].iloc[j]:
            j -= 1
        if j >= 0:
            ob = {
                "type": "bull",
                "idx": j,
                "high": float(df["high"].iloc[j]),
                "low": float(df["low"].iloc[j]),
                "time": df.index[j],
            }
            order_blocks.append(ob)

    # ---- Bearish OB ----
    elif t == "BOS_down":
        j = idx-1
        while j >= 0 and df["close"].iloc[j] <= df["open"].iloc[j]:
            j -= 1
        if j >= 0:
            ob = {
                "type": "bear",
                "idx": j,
                "high": float(df["high"].iloc[j]),
                "low": float(df["low"].iloc[j]),
                "time": df.index[j],
            }
            order_blocks.append(ob)

# ======================================================================
# 4) FAIR VALUE GAP (FVG) DETECTION (ICT 3-bar pattern)
# ======================================================================
fvg_list = []

for i in range(1, n-1):
    # Bullish FVG: low[i] > high[i-1]
    if low[i] > high[i-1]:
        fvg_list.append({
            "type": "bull",
            "idx": i,
            "low": float(high[i-1]),
            "high": float(low[i]),
            "time": df.index[i]
        })

    # Bearish FVG: high[i] < low[i-1]
    if high[i] < low[i-1]:
        fvg_list.append({
            "type": "bear",
            "idx": i,
            "low": float(high[i]),
            "high": float(low[i-1]),
            "time": df.index[i]
        })

# ======================================================================
# 5) PLOT SMC CHART
# ======================================================================
fig = go.Figure()

# ---- Price line (TradingView style) ----
fig.add_trace(go.Scatter(
    x=dates, y=close,
    mode="lines",
    line=dict(color="black", width=1.5),
    name="Price"
))

# ---- Plot Fair Value Gaps ----
for f in fvg_list:
    color = "rgba(0,150,255,0.25)" if f["type"]=="bull" else "rgba(255,120,0,0.25)"
    fig.add_trace(go.Scatter(
        x=[f["time"], f["time"], f["time"]],
        y=[f["low"], f["high"], f["low"]],
        fill="toself",
        fillcolor=color,
        line=dict(color=color),
        name="FVG",
        hoverinfo="skip",
        showlegend=False,
    ))

# ---- Plot Order Blocks ----
for ob in order_blocks:
    color = "rgba(0,200,0,0.3)" if ob["type"]=="bull" else "rgba(200,0,0,0.3)"
    fig.add_trace(go.Scatter(
        x=[ob["time"], ob["time"]],
        y=[ob["low"], ob["high"]],
        mode="lines",
        line=dict(color=color, width=8),
        name="Order Block",
        showlegend=False
    ))

# ---- Plot BOS / CHoCH markers ----
for s in structure:
    idx = s["idx"]
    c = "green" if "up" in s["type"] else "red"
    fig.add_trace(go.Scatter(
        x=[dates[idx]],
        y=[close[idx]],
        mode="markers+text",
        marker=dict(color=c, size=10),
        text=[s["type"]],
        textposition="top center",
        showlegend=False,
    ))

fig.update_layout(
    title="SMC - TradingView Style (BOS, CHoCH, OB, FVG)",
    height=900,
    xaxis_rangeslider_visible=False
)

fig.write_html(out_html)
print("Wrote:", out_html)