# backtest/orders.py

class Order:
    def __init__(self, type, price, size, sl=None, tp=None):
        self.type = type         # market / limit / stop
        self.price = price
        self.size = size
        self.sl = sl
        self.tp = tp
        self.active = True
