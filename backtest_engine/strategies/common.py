

import pandas as pd
import os
from pathlib import Path

def get_data_path(fname: str) -> Path:
    # find data dir relative to this file
    this_file = Path(__file__).resolve()
    for parent in this_file.parents[:6]:
        cand = parent / "data"
        if cand.is_dir():
            p = cand / fname
            if p.is_file():
                return p.resolve()
            # if not file but dir exists return dir for caller to inspect
            return cand.resolve()
    # fallback cwd
    if (Path.cwd() / "data").is_dir():
        return (Path.cwd() / "data" / fname).resolve()
    raise FileNotFoundError(f"Could not find '{fname}' in any data directories.")


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