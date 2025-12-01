

import pandas as pd

def clean_ohlc(df_raw: pd.DataFrame, timeframe: str = '1min') -> pd.DataFrame:
    """
    Chuẩn hoá OHLC cho mọi khung thời gian:
    timeframe ví dụ: '1min', '5min', '15min', '30min', '1h', '4h'
    """
    df = df_raw.copy()

    df.columns = [c.lower() for c in df.columns]
    # Convert open_time -> datetime
    df['open_time'] = pd.to_datetime(df['open_time'], errors='coerce')
    df = df.dropna(subset=['open_time'])

    # Set index
    df = df.set_index('open_time')
    df = df.sort_index()

    # Floor index theo timeframe
    df.index = df.index.floor(timeframe)

    # Capitalize column names
    df.columns = [c.lower() for c in df.columns]

    return df