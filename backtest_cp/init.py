from dotenv import load_dotenv
import os
from pprint import pprint
import pandas as pd
import datetime
import talib
import json
import time
from datetime import datetime
import pytz # Thư viện để quản lý múi giờ
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import altair as alt
from scipy.signal import find_peaks
import numpy as np


def resample_data(data_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Chuyển đổi dữ liệu từ khung thời gian nhỏ hơn sang khung thời gian lớn hơn
    (Resampling OHLCV và các cột khối lượng Taker).
    """
   
    # 1. Xử lý Index và kiểu dữ liệu (KHẮC PHỤC LỖI)
   
    # Đổi tên cột trong DataFrame sang chữ thường để dễ xử lý
    data_1m.columns = data_1m.columns.str.lower()
   
    # Nếu 'open_time' là cột (chưa phải index), chuyển đổi và đặt làm index
    if 'open_time' in data_1m.columns:
        # Chuyển đổi kiểu dữ liệu sang datetime (Rất quan trọng)
        data_1m['open_time'] = pd.to_datetime(data_1m['open_time'])
        # Đặt cột 'open_time' làm index
        data_1m.set_index('open_time', inplace=True)
 
    # Nếu index chưa phải DatetimeIndex, báo lỗi (chỉ để an toàn)
    if not isinstance(data_1m.index, pd.DatetimeIndex):
         raise TypeError("Index sau khi xử lý không phải DatetimeIndex. Kiểm tra lại dữ liệu.")
   
    # 2. Định nghĩa Quy tắc Aggregation
    ohlcv_agg = {
        'open': 'first',  
        'high': 'max',    
        'low': 'min',      
        'close': 'last',  
        'num_trades': 'sum',
        'taker_buy_base': 'sum',    
        'taker_buy_quote': 'sum',  
    }
   
    # Lọc lại agg_dict chỉ giữ các cột có tồn tại trong DataFrame
    valid_agg = {col: func for col, func in ohlcv_agg.items() if col in data_1m.columns}
 
    # 3. Thực hiện Resampling
    resampled_df = data_1m.resample(timeframe).agg(valid_agg)
   
    # 4. Loại bỏ các hàng NaN và trả về
    resampled_df.dropna(inplace=True)
   
    return resampled_df