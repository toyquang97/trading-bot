# check_equity_consistency.py
import pandas as pd
import numpy as np

fn = 'backtest_output_detailed_mtf.csv'   # đổi nếu file khác
df = pd.read_csv(fn, parse_dates=['open_time'])
df = df.set_index('open_time')
pd.set_option('display.max_rows', 50)

# detect column names (some project use 'entry' or 'entry_price')
entry_col = 'entry' if 'entry' in df.columns else ('entry_price' if 'entry_price' in df.columns else None)
close_col = 'Close' if 'Close' in df.columns else ('close' if 'close' in df.columns else None)
equity_col = 'equity' if 'equity' in df.columns else None
pnl_col = 'pnl' if 'pnl' in df.columns else ('pnl_pct' if 'pnl_pct' in df.columns else None)
side_col = 'side' if 'side' in df.columns else ('position_side' if 'position_side' in df.columns else None)

print("Detected cols:", entry_col, close_col, equity_col, pnl_col, side_col)
if not (entry_col and close_col and equity_col and side_col):
    raise SystemExit("Không tìm được column cần thiết trong CSV.")

# assume size = 1 if no size column
size_col = None
if 'size' in df.columns:
    size_col = 'size'
else:
    df['_size'] = 1.0
    size_col = '_size'

# compute expected unrealized pnl and expected equity for TradingView-style
def compute_tv_unrealized(entry, price, size, side):
    if pd.isna(entry) or pd.isna(price) or size == 0:
        return 0.0
    if side.lower().startswith('s'):  # Short
        return (entry - price) * abs(size)
    else:
        return (price - entry) * abs(size)

df['expected_unrealized'] = df.apply(lambda r: compute_tv_unrealized(r[entry_col], r[close_col], r[size_col], str(r[side_col]) if pd.notna(r[side_col]) else ''), axis=1)
# expected equity (TradingView-style)
# Need initial capital: infer from first equity if constant at start
initial_cap = None
if equity_col and not pd.isna(df.iloc[0][equity_col]):
    initial_cap = float(df.iloc[0][equity_col])
else:
    # fallback to 100000
    initial_cap = 100000.0

df['expected_equity_tv'] = initial_cap + df['expected_unrealized']

# expected equity (cash-accounting style) using position * price + capital column:
# Here we don't know capital flow history, skip full reconstruction unless trades available.
# We'll compute expected_equity_pos = (position * price) + capital_assumed (use initial_cap)
df['expected_equity_posmodel'] = initial_cap + (df[size_col].where(df[side_col].str.lower().str.startswith('l'), -df[size_col])) * df[close_col]

# compare to recorded equity
df['equity_diff_tv'] = df[equity_col] - df['expected_equity_tv']
df['equity_diff_posmodel'] = df[equity_col] - df['expected_equity_posmodel']

# show rows where difference big
TH = 1.0  # USD threshold
bad_tv = df[ df['equity_diff_tv'].abs() > TH ]
bad_pos = df[ df['equity_diff_posmodel'].abs() > TH ]

print("\nSample rows (head):")
print(df[[close_col, entry_col, size_col, side_col, 'expected_unrealized', equity_col, 'expected_equity_tv', 'equity_diff_tv']].head(20).to_string())

print(f"\nRows with |equity - expected_tv| > {TH}: {len(bad_tv)}")
if len(bad_tv):
    print(bad_tv[[close_col, entry_col, size_col, side_col, equity_col, 'expected_equity_tv', 'equity_diff_tv']].head(20).to_string())

print(f"\nRows with |equity - expected_posmodel| > {TH}: {len(bad_pos)}")
if len(bad_pos):
    print(bad_pos[[close_col, entry_col, size_col, side_col, equity_col, 'expected_equity_posmodel', 'equity_diff_posmodel']].head(20).to_string())
