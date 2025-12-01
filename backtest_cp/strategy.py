import os, importlib, pkgutil
import pandas as pd
import numpy as np
from init import *
from strategies.boll_vol import generate as strategy_generate



def generate_signals(df_1m: pd.DataFrame,
                     base_risk_pct: float = 0.01) -> pd.DataFrame:
    """
    Fixed entry point — không đổi chữ ký.
    Internally: loads strategies/active.py -> generate(df_1m, mtf_dict, base_risk_pct)
    If not present, uses a tiny builtin example.
    Returns a DataFrame indexed by 1m timestamps with columns:
      ['signal_side','note','size','risk_pct','tp_price','sl_price']
    """

    # Precompute MTF như cũ


    # Gọi chiến thuật và trả về kết quả
    return strategy_generate(df_1m, base_risk_pct)
