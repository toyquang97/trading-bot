from include import *



# --- Thiết lập API Keys (KHÔNG BẮT BUỘC cho Market Data) ---

# Nếu chỉ lấy dữ liệu thị trường (như Order Book), bạn không cần API Key,

# nhưng để có thói quen tốt và sẵn sàng cho các lệnh giao dịch sau này, bạn nên dùng.

# Thay thế bằng API Key và Secret thực tế của bạn



# --- Thiết lập Cấu hình ---

SYMBOL = 'BTCUSDT'  # Cặp giao dịch bạn muốn lấy Order Book

LIMIT = 100         # Số lượng mức giá (cả bids và asks) muốn lấy. Mặc định là 100, tối đa 1000.



N_DISPLAY = 5       # Chỉ hiển thị 5 mức giá tốt nhất

INTERVAL_S = 1      # Thời gian chờ giữa các lần cập nhật

# 1. Khởi tạo Client





def get_futures_order_book(symbol, limit):

    """

    Lấy snapshot Order Book từ API REST của Binance USDⓈ-M Futures.

    """

    print(f"--- Lấy Order Book Futures cho cặp {symbol} (Limit={limit}) ---")

   

    try:

        # Sử dụng hàm futures_order_book()

        depth = client.futures_order_book(symbol=symbol, limit=limit)

       

        # --- Phân tích dữ liệu ---

       

        # 2. Xử lý Bids (Lệnh MUA - Sắp xếp từ cao xuống thấp)

        bids = pd.DataFrame(depth['bids'], columns=['Price', 'Quantity'], dtype=float)

        bids['Side'] = 'Bid (Mua)'

        bids = bids.sort_values(by='Price', ascending=False).head(5)

       

        # 3. Xử lý Asks (Lệnh BÁN - Sắp xếp từ thấp lên cao)

        asks = pd.DataFrame(depth['asks'], columns=['Price', 'Quantity'], dtype=float)

        asks['Side'] = 'Ask (Bán)'

        asks = asks.sort_values(by='Price', ascending=True).head(5)

       

        # 4. Hiển thị thông tin

        last_update_id = depth.get('lastUpdateId', 'N/A')

        print(f"\nLast Update ID: {last_update_id}")

       

        print("\n--- BIDS (Lệnh Mua Cao nhất) ---")

        print(bids)

       

        print("\n--- ASKS (Lệnh Bán Thấp nhất) ---")

        print(asks)

       

        # 5. Thông tin thêm (Top of the Book/Spread)

        best_bid = bids['Price'].iloc[0]

        best_ask = asks['Price'].iloc[0]

        spread = best_ask - best_bid

       

        print(f"\nBest Bid (Giá Mua Tốt nhất): {best_bid}")

        print(f"Best Ask (Giá Bán Tốt nhất): {best_ask}")

        print(f"Spread (Chênh lệch): {spread:.2f}")



    except Exception as e:

        print(f"Đã xảy ra lỗi khi kết nối với Binance Futures: {e}")



def get_raw_futures_order_book(symbol, limit):

    """

    Lấy Order Book Futures thô và in ra (không sắp xếp, không chuyển đổi DataFrame).

    """

    print(f"--- Dữ liệu Order Book THÔ cho {symbol} (Limit={limit}) ---")

   

    try:

        # Sử dụng hàm futures_order_book()

        raw_depth = client.futures_order_book(symbol=symbol, limit=limit)

       

        # In ra toàn bộ kết quả thô

        print(json.dumps(raw_depth, indent=4))

       

        # --- Giải thích Cấu trúc ---

        print("\n--- Giải thích Cấu trúc ---")

       

        # Bids (Lệnh Mua)

        # Các cặp giá/số lượng này được API sắp xếp theo giá Giảm dần (Best Bid nằm trên cùng)

        print(f"Giá/Số lượng Bids (Mua) TỐT NHẤT (Sắp xếp GIẢM dần): {raw_depth['bids'][0]}")

       

        # Asks (Lệnh Bán)

        # Các cặp giá/số lượng này được API sắp xếp theo giá Tăng dần (Best Ask nằm trên cùng)

        print(f"Giá/Số lượng Asks (Bán) TỐT NHẤT (Sắp xếp TĂNG dần): {raw_depth['asks'][0]}")

       

    except Exception as e:

        print(f"Đã xảy ra lỗi khi kết nối với Binance Futures: {e}")



def get_top_n_futures_order_book(symbol, limit, n_display=10):

    """

    Lấy Order Book Futures (với limit tối đa) và chỉ in ra N mức giá tốt nhất.

    """

    print(f"--- Lấy Order Book Futures cho {symbol} (Limit={limit}) ---")

   

    try:

        # Lấy Order Book (ảnh chụp)

        depth = client.futures_order_book(symbol=symbol, limit=limit)

       

        # --- Phân tích và Hiển thị ---

       

        # 1. Xử lý Bids (Lệnh Mua)

        # API trả về Bids theo thứ tự GIÁ GIẢM DẦN (Tốt nhất là [0])

        bids = pd.DataFrame(depth['bids'], columns=['Price', 'Quantity'], dtype=float)

        bids['Side'] = 'Bid (Mua)'

       

        # 2. Xử lý Asks (Lệnh Bán)

        # API trả về Asks theo thứ tự GIÁ TĂNG DẦN (Tốt nhất là [0])

        asks = pd.DataFrame(depth['asks'], columns=['Price', 'Quantity'], dtype=float)

        asks['Side'] = 'Ask (Bán)'

       

        print(f"\nLast Update ID: {depth.get('lastUpdateId', 'N/A')}")

        print(f"Tổng số mức giá Bids đã lấy: {len(bids)}")

        print(f"Tổng số mức giá Asks đã lấy: {len(asks)}")



        # 3. Chỉ in ra N mức giá tốt nhất

        print(f"\n--- TOP {n_display} BIDS (Lệnh Mua Cao nhất) ---")

        # Do đã sắp xếp, chỉ cần lấy N hàng đầu tiên

        print(bids.head(n_display))

       

        print(f"\n--- TOP {n_display} ASKS (Lệnh Bán Thấp nhất) ---")

        # Do đã sắp xếp, chỉ cần lấy N hàng đầu tiên

        print(asks.head(n_display))

       

        # 4. Hiển thị Spread

        best_bid = bids['Price'].iloc[0]

        best_ask = asks['Price'].iloc[0]

        spread = best_ask - best_bid

        print(f"\nSpread (Chênh lệch giá mua/bán): {spread:.2f}")



    except Exception as e:

        print(f"Đã xảy ra lỗi khi kết nối với Binance Futures: {e}")

def get_latest_futures_price(symbol):

    """

    Lấy giá gần nhất (Mark Price) của cặp giao dịch Futures.

    """

    try:

        # Sử dụng API để lấy Mark Price (Giá Đánh dấu/Giá Thanh lý)

        # hoặc có thể dùng client.futures_symbol_ticker(symbol=symbol) để lấy Last Price

        ticker = client.futures_mark_price(symbol=symbol)

        price = float(ticker['markPrice'])

        return price

    except Exception as e:

        # Xử lý lỗi nếu không kết nối được API

        print(f"Lỗi khi lấy giá: {e}")

        return None



def continuous_price_display(symbol, interval_s=1):

    """

    Tạo vòng lặp while True để hiển thị giá liên tục.

    """

    print(f"--- Bắt đầu cập nhật giá {symbol} mỗi {interval_s} giây. Nhấn Ctrl+C để dừng ---")

   

    while True:

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        latest_price = get_latest_futures_price(symbol)

       

        if latest_price is not None:

            # Định dạng giá với 2 chữ số thập phân, hoặc tùy theo coin

            print(f"[{current_time}] Giá {symbol}: {latest_price:,.2f} USD")

           

        # Tạm dừng chương trình trong 'interval_s' giây

        time.sleep(interval_s)



def get_order_book_snapshot(symbol, limit):

    """

    Lấy snapshot Order Book từ API REST của Binance Futures.

    """

    try:

        # Lấy Order Book (ảnh chụp)

        depth = client.futures_order_book(symbol=symbol, limit=limit)

       

        # Xử lý Bids (Mua) và Asks (Bán)

        # Bids: Giá giảm dần (Tốt nhất là [0])

        bids = pd.DataFrame(depth['bids'], columns=['Price', 'Quantity'], dtype=float)

        # Asks: Giá tăng dần (Tốt nhất là [0])

        asks = pd.DataFrame(depth['asks'], columns=['Price', 'Quantity'], dtype=float)



        return bids, asks

       

    except Exception as e:

        # Xử lý lỗi (ví dụ: Rate Limit hoặc lỗi kết nối)

        print(f"\n[LỖI] Không thể lấy Order Book: {e}")

        return None, None



def continuous_order_book_display(symbol, limit, n_display, interval_s):

    """

    Tạo vòng lặp while True để hiển thị Order Book liên tục dạng cuốn chiếu.

    """

    print(f"--- Bắt đầu cập nhật Order Book {symbol} mỗi {interval_s} giây. Nhấn Ctrl+C để dừng ---")

   

    # Bắt đầu vòng lặp cập nhật

    while True:

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        bids, asks = get_order_book_snapshot(symbol, limit)

       

        if bids is not None and asks is not None:

           

            # --- Hiển thị Kết quả ---

            print("\n==================================================")

            print(f"[{current_time}] Cặp: {symbol} | Cập nhật: {limit} mức giá")

            print("==================================================")

           

            # 1. Bán (Asks) - Giá tăng dần (tốt nhất nằm trên cùng)

            print(f"--- TOP {n_display} ASKS (Bán Thấp nhất) ---")

            # Hiển thị N hàng đầu tiên

            print(asks.head(n_display).to_string(index=False))

           

            # 2. Spread

            best_bid = bids['Price'].iloc[0]

            best_ask = asks['Price'].iloc[0]

            spread = best_ask - best_bid

            print(f"\n  SPREAD: {spread:.2f} | BEST BID: {best_bid:,.2f} | BEST ASK: {best_ask:,.2f}")

           

            # 3. Mua (Bids) - Giá giảm dần (tốt nhất nằm trên cùng)

            print(f"\n--- TOP {n_display} BIDS (Mua Cao nhất) ---")

            # Hiển thị N hàng đầu tiên

            print(bids.head(n_display).to_string(index=False))



        # Tạm dừng chương trình

        time.sleep(interval_s)



# --- Thực thi hàm ---

try:

    continuous_order_book_display(SYMBOL, LIMIT, N_DISPLAY, INTERVAL_S)

except KeyboardInterrupt:

    print("\n--- Đã dừng cập nhật Order Book. ---")



# --- Thực thi hàm ---

# try:

#     continuous_price_display(SYMBOL, interval_s=1)

# except KeyboardInterrupt:

#     print("\n--- Đã dừng cập nhật giá. ---")

# --- Thực thi hàm (chỉ in ra 10 mức giá) ---

# get_top_n_futures_order_book(SYMBOL, LIMIT, n_display=10)

# --- Thực thi hàm ---

# get_raw_futures_order_book(SYMBOL, LIMIT)

# --- Thực thi hàm ---

       

# get_futures_order_book(SYMBOL, LIMIT)