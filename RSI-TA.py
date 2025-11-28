from include import *
import os
import pandas as pd

# use data folder path
FILE_PATH = os.path.join(os.path.dirname(__file__), "data", "BTCUSDT_4h_20251101_0000_to_20251120_2359.csv")

RSI_PERIOD = 14

# column name for time (keep as provided)
TIME_COLUMN_NAME = 'open_time'


def _normalize_df_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to lowercase and strip whitespace."""
    df = df.rename(columns=lambda c: c.strip().lower())
    return df

def visualize_interactive_btc_rsi(file_path, rsi_period, time_col_name):
    print(f"-> Đang đọc dữ liệu từ file: {file_path}")
    df = pd.read_csv(file_path)

    df = _normalize_df_columns(df)
    time_col = time_col_name.lower()

    if time_col not in df.columns:
        raise KeyError(time_col)

    df[time_col] = pd.to_datetime(df[time_col], utc=True).dt.tz_convert(None)
    df.set_index(time_col, inplace=True)

    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # RSI
    df["rsi"] = talib.RSI(df["close"], timeperiod=rsi_period)
    df.dropna(inplace=True)

    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
    )

    # ⚡️ ScatterGL CLOSE PRICE (nhanh gấp 50 lần so với Candlestick)
    fig.add_trace(go.Scattergl(
        x=df.index,
        y=df['close'],
        mode='lines',
        line=dict(color='black'),
        name='BTC Price'
    ), row=1, col=1)

    # RSI
    fig.add_trace(go.Scattergl(
        x=df.index,
        y=df['rsi'],
        mode='lines',
        line=dict(color='purple'),
        name='RSI'
    ), row=2, col=1)

    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.update_layout(
        title=f"BTC RSI ({rsi_period}) - Optimized Fast Render",
        height=700,
        xaxis_rangeslider_visible=False,
        hovermode=False,      # ⚡ tắt hover unified để tăng tốc
        template="plotly_white"
    )

    fig.show()


def calculate_and_save_rsi(input_filepath, rsi_period=14, output_suffix='_with_RSI'):
    """
    Read CSV, compute RSI, save new CSV. Normalizes columns to lowercase.
    """
    try:
        df = pd.read_csv(input_filepath)
        df = _normalize_df_columns(df)

        CLOSE_COL = 'close'
        if CLOSE_COL not in df.columns:
            print(f"LỖI: Không tìm thấy cột '{CLOSE_COL}' trong file.")
            return None

        df[CLOSE_COL] = pd.to_numeric(df[CLOSE_COL], errors="coerce")
        print(f"-> Đang tính toán RSI ({rsi_period} kỳ)...")
        df[f'rsi_{rsi_period}'] = talib.RSI(df[CLOSE_COL], timeperiod=rsi_period)

        base_name, ext = os.path.splitext(input_filepath)
        output_filepath = f"{base_name}{output_suffix}{ext}"
        df.to_csv(output_filepath, index=False)
        print(f"✅ ĐÃ XỬ LÝ THÀNH CÔNG! File: {output_filepath}")
        return output_filepath

    except FileNotFoundError:
        print(f"LỖI: Không tìm thấy file tại đường dẫn: {input_filepath}")
        return None
    except Exception as e:
        print(f"Đã xảy ra lỗi không xác định: {e}")
        return None


# execute
visualize_interactive_btc_rsi(FILE_PATH, RSI_PERIOD, TIME_COLUMN_NAME)