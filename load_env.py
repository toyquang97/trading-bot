
import os
from dotenv import load_dotenv
from binance.client import Client
# load .env từ cùng thư mục file này
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

# LẤY THEO TÊN BIẾN MÔI TRƯỜNG (KHÔNG PHẢI VALUE)
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
# Kết nối testnet/demo (đổi testnet=False nếu dùng live)

USE_TESTNET = True
client = Client(API_KEY, API_SECRET, testnet=USE_TESTNET)