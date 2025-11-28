# order_client.py
"""
Đơn giản hóa: module chỉ để đặt lệnh trên Binance USDT-M Futures.
Hàm chính:
    place_order(order: dict) -> dict  # đặt 1 lệnh
    place_orders(order_list: list) -> list  # đặt nhiều lệnh

Order dict mẫu:
{
  "symbol": "BTCUSDT",
  "side": "BUY" or "SELL",
  # CHỌN 1 trong 2:
  "usdt": 10.0,        # muốn dùng ~10 USDT (hàm tự tính qty)
  "quantity": 0.001,   # hoặc chỉ định trực tiếp base qty
  "type": "MARKET" or "LIMIT",
  "price": 12345.0,    # bắt buộc nếu type == "LIMIT"
  "leverage": 3        # optional, dùng khi tính qty từ usdt
}
"""

import os
import math
import logging
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
import math

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


USE_TESTNET = os.getenv("USE_TESTNET", "True").lower() in ("1", "true", "yes")

# load .env từ cùng thư mục file này
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

# LẤY THEO TÊN BIẾN MÔI TRƯỜNG (KHÔNG PHẢI VALUE)
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

if not API_KEY or not API_SECRET:
    raise SystemExit("Missing BINANCE_API_KEY / BINANCE_API_SECRET in .env")

# client (public + private)
client = Client(API_KEY, API_SECRET, testnet=USE_TESTNET)

# ---------- Helpers ----------
def get_symbol_info(symbol):
    info = client.futures_exchange_info()
    for s in info.get("symbols", []):
        if s.get("symbol") == symbol:
            return s
    raise ValueError(f"Symbol {symbol} not found")

def get_filter_value(symbol_info, filter_type, key):
    for f in symbol_info.get("filters", []):
        if f.get("filterType") == filter_type:
            return f.get(key)
    return None

def round_down_qty(qty, step_size_str):
    """
    Round down `qty` to the nearest multiple of step_size.
    """
    step = float(step_size_str)
    if step <= 0:
        return 0.0
    # precision = số chữ số thập phân
    precision = int(round(-math.log10(step))) if step < 1 else 0
    factor = 10 ** precision
    # round down qty to the precision
    q = math.floor(qty * factor) / factor
    # align to multiple of step
    q = math.floor(q / step) * step
    # tránh -0.0
    if q < 0:
        q = 0.0
    return float(round(q, precision))

def get_price(symbol):
    tick = client.futures_symbol_ticker(symbol=symbol)
    return float(tick["price"])

def compute_qty_from_usdt(symbol, usdt_amount, leverage=1, safety=0.99, verbose=False):
    """Tính qty = (usdt * leverage * safety) / price, rồi round down theo stepSize.
    Ghi log các bước để debug tại sao qty cuối cùng khác kỳ vọng.
    """
    price = get_price(symbol)
    lev = max(1, int(leverage))
    raw = (usdt_amount * lev * safety) / price

    s_info = get_symbol_info(symbol)
    step = get_filter_value(s_info, "LOT_SIZE", "stepSize") or "0.000001"
    # precision = số chữ số thập phân theo step
    try:
        precision = int(round(-math.log10(float(step)))) if float(step) < 1 else 0
    except Exception:
        precision = 8

    qty = round_down_qty(raw, step)
    notional = qty * price
    effective_usdt = notional / lev  # số USDT thực tế dùng (sau leverage)
    if verbose:
        logging.info(
            "compute_qty_from_usdt: symbol=%s price=%s usdt=%s leverage=%s safety=%s raw=%s step=%s precision=%s qty=%s notional=%s effective_usdt=%s",
            symbol, price, usdt_amount, lev, safety, raw, step, precision, qty, notional, effective_usdt
        )
    return qty

def ensure_qty_ok(symbol, qty):
    s_info = get_symbol_info(symbol)
    minQty = float(get_filter_value(s_info, "LOT_SIZE", "minQty") or 0)
    maxQty = float(get_filter_value(s_info, "LOT_SIZE", "maxQty") or 0)
    minNotional = float(get_filter_value(s_info, "MIN_NOTIONAL", "minNotional") or 0)
    price = get_price(symbol)
    notional = qty * price
    if qty <= 0:
        return False, "qty <= 0"
    if minQty and qty < minQty:
        return False, f"qty {qty} < minQty {minQty}"
    if maxQty and qty > maxQty:
        return False, f"qty {qty} > maxQty {maxQty}"
    if minNotional and notional < minNotional:
        return False, f"notional {notional:.6f} < minNotional {minNotional}"
    return True, "OK"

# ---------- Order primitives ----------
def _place_market(symbol, side, quantity, reduceOnly=False):
    try:
        resp = client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=quantity,
            reduceOnly=reduceOnly
        )
        logging.info("MARKET order placed: %s %s qty=%s", side, symbol, quantity)
        return resp
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error("Market order error: %s", e)
        raise
    except Exception as e:
        logging.exception("Unexpected market order error: %s", e)
        raise

def _place_limit(symbol, side, quantity, price, timeInForce="GTC", reduceOnly=False):
    try:
        resp = client.futures_create_order(
            symbol=symbol,
            side=side,
            type="LIMIT",
            timeInForce=timeInForce,
            quantity=quantity,
            price=str(price),
            reduceOnly=reduceOnly
        )
        logging.info("LIMIT order placed: %s %s qty=%s price=%s", side, symbol, quantity, price)
        return resp
    except Exception as e:
        logging.exception("Limit order error: %s", e)
        raise

# ---------- Public API of module ----------
def get_current_position_qty(symbol):
    """Return current net position amount (positive long, negative short)."""
    try:
        pos = client.futures_position_information(symbol=symbol)
    except Exception:
        return 0.0
    for p in pos:
        if p.get("symbol") == symbol:
            return float(p.get("positionAmt", 0) or 0.0)
    return 0.0

def set_symbol_leverage(symbol, leverage):
    """Thử set leverage cho symbol trên Binance (no-op nếu thất bại)."""
    try:
        resp = client.futures_change_leverage(symbol=symbol, leverage=int(leverage))
        logging.info("Leverage set for %s -> %s", symbol, leverage)
        return resp
    except Exception as e:
        logging.warning("Could not set leverage for %s: %s", symbol, e)
        return None

def place_order(order: dict):
    """
    Đặt 1 lệnh theo order dict (xem định dạng ở đầu file).
    Trả về response của Binance (dict) hoặc raise exception.
    """
    symbol = order.get("symbol")
    side = order.get("side")
    typ = order.get("type", "MARKET").upper()
    leverage = int(order.get("leverage", 1))

    if symbol is None or side is None:
        raise ValueError("order must include 'symbol' and 'side'")

    # ensure exchange leverage matches requested leverage (important!)
    set_symbol_leverage(symbol, leverage)

    # compute qty
    qty = None
    if order.get("quantity") is not None:
        qty = float(order["quantity"])
    elif order.get("usdt") is not None:
        # compute_qty_from_usdt nhận leverage làm tham số — nhưng cần set leverage trên sàn trước
        qty = compute_qty_from_usdt(symbol, float(order["usdt"]), leverage=leverage)
    else:
        raise ValueError("order must include 'quantity' or 'usdt'")

    logging.info("Placing order: symbol=%s side=%s qty=%s leverage=%s type=%s", symbol, side, qty, leverage, typ)
    # check qty rules (minQty / minNotional / maxQty)
    ok, reason = ensure_qty_ok(symbol, qty)
    if not ok:
        raise ValueError(f"Qty validation failed: {reason}")

    # check exchange-level max position (prevent -2027)
    s_info = get_symbol_info(symbol)
    max_pos = s_info.get("maxPosition") or s_info.get("maxQty") or None
    try:
        max_pos = float(max_pos) if max_pos is not None else None
    except Exception:
        max_pos = None

    if max_pos and max_pos > 0:
        current = get_current_position_qty(symbol)
        remaining = max_pos - abs(current)
        if qty > remaining:
            raise ValueError(
                f"Order qty {qty} would exceed max position {max_pos}. "
                f"Current pos={current}, remaining capacity={remaining:.8f}. "
                "Reduce qty or lower leverage."
            )

    # place order
    try:
        if typ == "MARKET":
            return _place_market(symbol, side, qty, reduceOnly=False)
        elif typ == "LIMIT":
            price = order.get("price")
            if price is None:
                raise ValueError("LIMIT order requires 'price'")
            return _place_limit(symbol, side, qty, price, timeInForce=order.get("timeInForce", "GTC"), reduceOnly=False)
        else:
            raise ValueError(f"Unsupported order type: {typ}")
    except BinanceAPIException as e:
        # surface Binance message for easier debugging
        raise ValueError(f"Binance API error placing order: {e}") from e

def place_orders(order_list):
    """Đặt nhiều lệnh, trả về list kết quả (response hoặc exception text)."""
    results = []
    for o in order_list:
        try:
            resp = place_order(o)
            results.append({"order": o, "response": resp})
        except Exception as e:
            logging.error("Order failed: %s -> %s", o, e)
            results.append({"order": o, "error": str(e)})
    return results

# ---------- Example usage if run directly ----------
if __name__ == "__main__":
    # Chỉ ví dụ; chỉnh ORDERS hoặc import module trong main.py
    ORDERS = [
        {"symbol": "BTCUSDT", "side": "BUY", "usdt": 5.0, "type": "MARKET", "leverage": 3},
        {"symbol": "ETHUSDT", "side": "SELL", "quantity": 0.01, "type": "MARKET"},
    ]
    print(place_orders(ORDERS))
