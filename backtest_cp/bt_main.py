# bt_main.py
from engine import BacktestEngine
from strategy import generate_signals
from evaluation import calculate_performance_metrics
import pandas as pd
import numpy as np
import warnings
from init import clean_ohlc
warnings.filterwarnings("ignore", category=FutureWarning, message=".*deprecated.*")
 
# load your 1m data here. Example fallback if file not found:
file_path = 'BTCUSDT_1m_20251001_0000_to_20251127_2359.csv'
 
df_1m_raw = pd.read_csv(file_path)
# expected columns: Open, High, Low, Close, Volume, Time or index timestamp
df_1m = clean_ohlc(df_1m_raw, timeframe='1min')
# timezone handling (choose one)
if df_1m.index.tz is None:
    df_1m = df_1m.tz_localize('Asia/Ho_Chi_Minh')
else:
    df_1m = df_1m.tz_convert('Asia/Ho_Chi_Minh')
 
if __name__ == '__main__':
    print("🚀 Bắt đầu Backtest (MTF workflow)...")
    INITIAL_CAPITAL = 1000.0
    TAKER_FEE = 0.00075
    SIZE = 1
    LEVERAGE = 2
    # 1) Generate signals from strategy (strategy does resample + indicators internally)
    signals = generate_signals(df_1m, base_risk_pct=SIZE)
    # Optional: inspect non-empty signals
    num_signals = signals['signal_side'].count()
    print(f"Signals generated: {signals['signal_side'].count()} non-null entries")
    if num_signals == 0:
        print("❌ Không có tín hiệu nào → Dừng backtest.")
        exit()   # hoặc return nếu chạy trong hàm

    # 2) Run engine with slippage and risk_pct support
    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL, fee_rate=TAKER_FEE,
                            slippage_pct=0.0002, slippage_ticks=0.0,
                            tick_size=0.0, leverage=LEVERAGE)
    output_data, trades_df = engine.run_backtest(df_1m, signals_df=signals, prefer_risk_pct=True)
 
    # 3) Evaluate
    equity_curve = output_data['equity'].dropna()
    if equity_curve.empty:
        print("❌ Không có đủ dữ liệu hoặc không có giao dịch được thực hiện.")
    else:
        metrics = calculate_performance_metrics(equity_curve, trades_df)
        print("\n" + "="*40)
        print("📊 KẾT QUẢ HIỆU SUẤT BACKTEST")
        print("="*40)
        for k,v in metrics.items():
            if '---' in k:
                print("\n" + k.replace('---',''))
            else:
                print(f"{k:<30}: {v}")
 
    # ----- START: robust export block (replace the old export try/except) -----
    try:
        # Helper: tìm tên cột thực tế trong output_data cho 'Close'
        def find_col(df, candidates):
            for c in candidates:
                if c in df.columns:
                    return c
                if c.lower() in df.columns:
                    return c.lower()
                if c.capitalize() in df.columns:
                    return c.capitalize()
                if c.upper() in df.columns:
                    return c.upper()
            return None
 
        close_col = find_col(output_data, ['Close', 'close', 'Close_price', 'ClosePrice', 'price'])
        if close_col is None:
            # fallback: take first numeric column as price (best-effort)
            numeric_cols = output_data.select_dtypes(include=['number']).columns.tolist()
            close_col = numeric_cols[0] if numeric_cols else None
 
        # Define which columns to keep, replacing 'Close' with actual column name found
        columns_to_keep = [close_col, 'entry_price', 'tp_price', 'sl_price', 'pnl_pct', 'equity', 'position_side']
        # Filter only those columns that actually exist in output_data
        columns_to_keep = [c for c in columns_to_keep if c is not None and c in output_data.columns]
 
        if len(columns_to_keep) == 0:
            raise ValueError("Không tìm thấy cột hợp lệ để xuất trong output_data.")
 
        df_output = output_data[columns_to_keep].copy()
 
        # Rename columns to friendly names if they exist
        rename_map = {}
        if close_col and close_col in df_output.columns:
            rename_map[close_col] = 'Close'
        if 'entry_price' in df_output.columns:
            rename_map['entry_price'] = 'entry'
        if 'tp_price' in df_output.columns:
            rename_map['tp_price'] = 'tp'
        if 'sl_price' in df_output.columns:
            rename_map['sl_price'] = 'sl'
        if 'pnl_pct' in df_output.columns:
            rename_map['pnl_pct'] = 'roi %'
        if 'position_side' in df_output.columns:
            rename_map['position_side'] = 'side'
        df_output.rename(columns=rename_map, inplace=True)
 
        # Export CSVs
        df_output.to_csv('backtest_output_detailed_mtf.csv')
        trades_df.to_csv('backtest_trades_summary_mtf.csv', index=False)
        print("✅ Xuất file output thành công.")
        print("DEBUG: Xuất các cột:", df_output.columns.tolist())
        print("DEBUG: Xuất các cột:", trades_df.columns.tolist())
 
    except Exception as e:
        print(f"❌ Lỗi khi xuất file: {e}")
        # debug info to help find issue
        try:
            print("DEBUG output_data columns:", output_data.columns.tolist())
            print("DEBUG trades_df columns:", trades_df.columns.tolist() if trades_df is not None else 'None')
        except Exception:
            pass
    # ----- END: robust export block -----
 