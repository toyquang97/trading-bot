# main.py
from order import place_order, place_orders

# Ví dụ 1 lệnh
orderBTC = {"symbol": "ETHUSDT", "side": "BUY", "usdt": 1000, "type": "MARKET", "leverage": 10}
# resp = place_order(order)
# print("Resp:", resp)

# Hoặc nhiều lệnh
orderALT = [
    {"symbol": "BTCUSDT", "side": "BUY", "usdt": 5.0, "type": "MARKET", "leverage": 3},
    {"symbol": "ADAUSDT", "side": "SELL", "quantity": 10, "type": "MARKET"},
]
# results = place_orders(orders)
# print(results)

# tạo hàm return dict order và hàm này truyền vào dict order trong main.py


# hàm returm orberBTC để sử dụng trong main.py
