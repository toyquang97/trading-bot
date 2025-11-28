from dotenv import load_dotenv
import os
from binance.client import Client
from pprint import pprint
import pandas as pd
import datetime
from load_env import *
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