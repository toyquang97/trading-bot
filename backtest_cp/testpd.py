from strategy import generate_signals   # or wherever your function is
from strategy import debug_generate_signals  # if you placed wrapper there
from init import *

file_path = 'BTCUSDT_1m_20251001_0000_to_20251127_2359.csv'
 
df = pd.read_csv(file_path)
debug_out = debug_generate_signals(df, generate_signals)
print