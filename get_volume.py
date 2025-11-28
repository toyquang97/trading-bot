from include import *
 
# --- Thiết lập Cấu hình ---
 
SYMBOL = 'BTCUSDT'  # Cặp giao dịch Futures
INTERVAL = Client.KLINE_INTERVAL_15MINUTE # Khung thời gian 15 phút
LIMIT = 30          # Số lượng cây nến gần nhất
 
 
def get_recent_futures_volume_vietnam_time(symbol, interval, limit):
    """
    Lấy dữ liệu K-Lines từ Binance Futures và chuyển đổi thời gian mở nến sang GMT+7.
    """
    print(f"--- Lấy dữ liệu {limit} cây nến {interval} gần nhất cho {symbol} (GMT+7) ---")
   
    try:
        # Lấy dữ liệu nến (klines)
        klines = client.futures_klines(
            symbol=symbol,
            interval=interval,
            limit=limit
        )
       
        # 1. Tạo DataFrame
        df = pd.DataFrame(klines, columns=[
            'Open time', 'Open', 'High', 'Low', 'Close', 'Volume',
            'Close time', 'Quote asset volume', 'Number of trades',
            'Taker buy base asset volume', 'Taker buy quote asset volume', 'Ignore'
        ])
       
        # 2. Chuyển đổi thời gian và giá trị
        df['Open time'] = pd.to_datetime(df['Open time'], unit='ms')
        df['Volume'] = df['Volume'].astype(float)
       
        # 3. ⭐️ CHUYỂN ĐỔI MÚI GIỜ (TỪ UTC SANG ASIA/HO_CHI_MINH) ⭐️
       
        # a) Gán múi giờ gốc (UTC)
        df['Open time'] = df['Open time'].dt.tz_localize(pytz.utc)
       
        # b) Chuyển đổi sang múi giờ Việt Nam (Asia/Ho_Chi_Minh là GMT+7)
        vn_timezone = pytz.timezone('Asia/Ho_Chi_Minh')
        df['Open time (VN)'] = df['Open time'].dt.tz_convert(vn_timezone)
       
        # 4. Chỉ giữ lại cột thời gian Việt Nam và Volume
        volume_data = df[['Open time (VN)', 'Volume']]
       
        return volume_data
 
    except Exception as e:
        print(f"Đã xảy ra lỗi khi lấy dữ liệu K-Lines: {e}")
        return None
 
# --- Thực thi hàm và hiển thị kết quả ---
volume_history_vn = get_recent_futures_volume_vietnam_time(SYMBOL, INTERVAL, LIMIT)
 
if volume_history_vn is not None:
    print("\n--- Volume của 30 cây nến 15 phút gần nhất (Giờ Việt Nam) ---")
    print(volume_history_vn)