# backtest/funding.py
from include import *

def load_funding_csv(path):
    df = pd.read_csv(path)
    df["fundingRate"] = df["fundingRate"].astype(float)
    return df.set_index("timestamp")["fundingRate"]
