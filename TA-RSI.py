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
    """
    Đọc dữ liệu BTC từ file CSV, tính toán RSI và vẽ biểu đồ tương tác bằng Plotly.
    """
    try:
        print(f"-> Đang đọc dữ liệu từ file: {file_path}")
        df = pd.read_csv(file_path)

        # normalize column names to lowercase
        df = _normalize_df_columns(df)
        time_col = time_col_name.lower()

        if time_col not in df.columns:
            raise KeyError(time_col)

        print(f"-> Đang sử dụng cột '{time_col}' làm chỉ mục thời gian.")
        # parse datetime (handles timezone-aware strings like +07:00)
        df[time_col] = pd.to_datetime(df[time_col], utc=True).dt.tz_convert(None)
        df.set_index(time_col, inplace=True)

        # ensure price columns exist and are numeric (csv uses open/high/low/close lowercase)
        for col in ("open", "high", "low", "close"):
            if col not in df.columns:
                raise KeyError(col)
            df[col] = pd.to_numeric(df[col], errors="coerce")

        close_prices = df["close"]

        print(f"-> Đang tính toán RSI ({rsi_period} kỳ) bằng TA-Lib...")
        df["rsi"] = talib.RSI(close_prices, timeperiod=rsi_period)
        df.dropna(inplace=True)

        if df.empty:
            print("LỖI: DataFrame rỗng sau khi xử lý dữ liệu. Vui lòng kiểm tra lại số lượng dữ liệu.")
            return

        # plotting
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3],
            subplot_titles=('Giá BTC Futures', f'Chỉ số RSI ({rsi_period})')
        )

        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Giá BTC',
            hovertemplate = '<b>Thời gian: %{x|%Y-%m-%d %H:%M:%S}</b><br>'
                            'Open: %{open:.2f}<br>'
                            'High: %{high:.2f}<br>'
                            'Low: %{low:.2f}<br>'
                            'Close: %{close:.2f}<extra></extra>'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['rsi'],
            name=f'RSI ({rsi_period})',
            line=dict(color='purple'),
            hovertemplate = '<b>Thời gian: %{x|%Y-%m-%d %H:%M:%S}</b><br>'
                            'RSI: %{y:.2f}<extra></extra>'
        ), row=2, col=1)

        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1, annotation_text="Quá mua (70)", annotation_position="top left")
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1, annotation_text="Quá bán (30)", annotation_position="bottom left")

        fig.update_layout(
            title_text=f'Biểu đồ Tương tác Giá BTC và RSI ({rsi_period})',
            xaxis_rangeslider_visible=False,
            height=700,
            hovermode="x unified",
            template="plotly_white"
        )

        fig.update_yaxes(range=[0, 100], row=2, col=1)
        fig.show()

    except FileNotFoundError:
        print(f"\nLỖI: Không tìm thấy file tại đường dẫn: {file_path}")
    except KeyError as e:
        print(f"\nLỖI KEY: Không tìm thấy cột: {e}. Vui lòng kiểm tra lại tên cột trong file CSV của bạn.")
    except Exception as e:
        print(f"\nĐã xảy ra lỗi không xác định: {e}")


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