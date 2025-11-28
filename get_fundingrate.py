from include import *
 
def get_futures_funding_rate_history_client(symbol, start_time_str=None, end_time_str=None):
    """
    Lấy lịch sử Funding Rate cho một cặp giao dịch Binance USDT-M Futures,
    sử dụng binance.client.Client.
    """
   
    # 1. Khởi tạo Client
    try:
        # Client cần API Key và Secret, ngay cả cho public endpoint này
        client = Client(API_KEY, API_SECRET)
        print("Đã khởi tạo Binance Client. Đang kết nối...")
    except Exception as e:
        print(f"❌ Lỗi khởi tạo client: {e}")
        return pd.DataFrame(columns=['Time', 'Symbol', 'Funding_Rate'])
 
    # 2. Xử lý Time Stamps (Chuyển đổi từ string sang timestamp miligiây)
    start_ts = None
    end_ts = None
   
    if start_time_str:
        start_dt = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
        start_ts = int(start_dt.timestamp() * 1000)
 
    if end_time_str:
        end_dt = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S')
        end_ts = int(end_dt.timestamp() * 1000)
 
    # 3. Tiến hành lấy dữ liệu với Phân trang
    all_data = []
    current_start_time = start_ts
    limit = 1000
    symbol = symbol.upper()
 
    print(f"Bắt đầu lấy dữ liệu Funding Rate cho cặp {symbol}...")
   
    while True:
        try:
            params = {
                'symbol': symbol,
                'limit': limit
            }
            if current_start_time:
                params['startTime'] = current_start_time
            if end_ts:
                params['endTime'] = end_ts
 
            data = client.futures_funding_rate(**params)
           
            if not data:
                break
               
            # 4. Xử lý và làm sạch dữ liệu
            df = pd.DataFrame(data)
            df = df.rename(columns={
                'fundingRate': 'Funding_Rate',
                'fundingTime': 'Time',
                'symbol': 'Symbol'
            })
           
            df['Time'] = pd.to_datetime(df['Time'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Ho_Chi_Minh') # Chuyển đổi sang múi giờ Việt Nam
            df['Funding_Rate'] = df['Funding_Rate'].astype(float)
            df = df[['Time', 'Symbol', 'Funding_Rate']]
            all_data.append(df)
           
            # 5. Cập nhật thời gian cho lần lặp tiếp theo
            if len(data) < limit:
                break
 
            next_start_time = data[-1]['fundingTime'] + 1
           
            if end_ts and next_start_time > end_ts:
                break
           
            current_start_time = next_start_time
            time.sleep(0.1)
 
        except Exception as e:
            print(f"❌ Lỗi khi gọi API. Vui lòng kiểm tra lại API Key/Secret và quyền truy cập Futures: {e}")
            break
   
    # 6. Gộp kết quả
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        final_df = final_df.drop_duplicates(subset=['Time', 'Symbol'])
        return final_df.sort_values(by='Time').reset_index(drop=True)
   
    return pd.DataFrame(columns=['Time', 'Symbol', 'Funding_Rate'])
 
# =========================================================================
 
## 🌐 Thiết lập Khung Giờ Việt Nam (UTC+7)
 
# 1. Xác định thời điểm hiện tại và thời điểm 7 ngày trước theo múi giờ Việt Nam
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
now_vn = datetime.now(VN_TZ)
seven_days_ago_vn = now_vn - timedelta(days=7)
 
# 2. Chuyển đổi thành chuỗi format 'YYYY-MM-DD HH:MM:SS'
start_str = seven_days_ago_vn.strftime('%Y-%m-%d %H:%M:%S')
end_str = now_vn.strftime('%Y-%m-%d %H:%M:%S')
 
print(f"--- THÔNG SỐ THỜI GIAN ---")
print(f"Múi giờ hiện tại: {VN_TZ.zone}")
print(f"Thời điểm BẮT ĐẦU: {start_str}")
print(f"Thời điểm KẾT THÚC: {end_str}")
print("-" * 50)
 
# 3. Gọi hàm để lấy dữ liệu
btc_funding_df = get_futures_funding_rate_history_client(
    symbol='BTCUSDT',
    start_time_str=start_str,
    end_time_str=end_str
)
 
## 📊 Kết quả Thử nghiệm
if not btc_funding_df.empty:
    print("\n✅ Tải dữ liệu thành công. Hiển thị 5 bản ghi cuối (gần nhất):")
    print("-" * 50)
    print(btc_funding_df.tail())
    print("-" * 50)
    print(f"Tổng số bản ghi đã tải: {len(btc_funding_df)}")
    print(f"Múi giờ của dữ liệu: {btc_funding_df['Time'].dt.tz}")
else:
    print("\n❌ Không thể tải dữ liệu. Vui lòng kiểm tra API Key/Secret.")