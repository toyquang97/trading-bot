# trade_executor.py
import os
import math
import logging
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException
import time
from load_env import *

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")



# ---------------- helpers ----------------
def get_symbol_info(symbol):
    info = client.futures_exchange_info()
    for s in info.get("symbols", []):
        if s.get("symbol") == symbol:
            return s
    raise ValueError(f"Symbol {symbol} not found in exchangeInfo")

def get_filter_value(symbol_info, filter_type, key):
    for f in symbol_info.get("filters", []):
        if f.get("filterType") == filter_type:
            return f.get(key)
    return None

def round_down_qty(qty, step_size_str):
    step = float(step_size_str)
    if step <= 0:
        return 0.0
    # precision from step
    precision = max(0, int(round(-math.log10(step)))) if step < 1 else 0
    factor = 10 ** precision
    q = math.floor(qty * factor) / factor
    q = math.floor(q / step) * step
    return float(round(q, precision))

def get_price(symbol):
    tick = client.futures_symbol_ticker(symbol=symbol)
    return float(tick["price"])

def compute_qty_from_usdt(symbol, usdt_amount, leverage=1, safety=0.995):
    price = get_price(symbol)
    raw = (usdt_amount * leverage * safety) / price
    s_info = get_symbol_info(symbol)
    step = get_filter_value(s_info, "LOT_SIZE", "stepSize") or "0.000001"
    qty = round_down_qty(raw, step)
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

# ---------------- core executor ----------------
def place_market_and_set_tp(symbol,
                           side,
                           amount_usdt=None,
                           quantity=None,
                           leverage=1,
                           take_profit_pct=0.02,
                           tp_using_mark_price=True,
                           wait_after_fill=0.5):
    """
    Place MARKET order to open position then create TAKE_PROFIT_MARKET to close position at TP.

    Params:
      - symbol: e.g. "BTCUSDT"
      - side: "BUY" or "SELL" for opening
      - amount_usdt: desired USDT exposure (preferred) OR
      - quantity: base asset qty (alternative)
      - leverage: used to compute qty from usdt (does NOT set account leverage)
      - take_profit_pct: TP percent (0.02 = 2%)
      - tp_using_mark_price: if True set workingType='MARK_PRICE' (recommended)
      - wait_after_fill: seconds to sleep briefly after placing market order to let position update

    Returns:
      dict with keys: ok(bool), open_order_resp, tp_order_resp, details...
    """
    if (amount_usdt is None) and (quantity is None):
        return {"ok": False, "error": "Provide amount_usdt or quantity"}

    # compute qty
    if quantity is None:
        qty = compute_qty_from_usdt(symbol, amount_usdt, leverage=leverage)
    else:
        qty = float(quantity)

    # ensure qty ok
    ok, reason = ensure_qty_ok(symbol, qty)
    if not ok:
        return {"ok": False, "error": f"Qty validation failed: {reason}"}

    # place market order to open
    try:
        logging.info(f"Placing MARKET order: symbol={symbol} side={side} qty={qty} leverage={leverage}")
        open_resp = client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=qty
        )
        logging.info("Market order resp: %s", {k: open_resp.get(k) for k in ("orderId","status","executedQty","avgPrice","cumQuote")})
    except BinanceAPIException as e:
        logging.error("Market order failed: %s", e)
        return {"ok": False, "error": f"Market order failed: {e.message if hasattr(e,'message') else str(e)}"}
    except Exception as e:
        logging.exception("Unexpected market order error")
        return {"ok": False, "error": str(e)}

    # wait a bit to ensure position exists / mark price updated
    time.sleep(wait_after_fill)

    # fetch mark/last price and position info
    try:
        mark = client.futures_mark_price(symbol=symbol)
        mark_price = float(mark.get("markPrice") or mark.get("price") or get_price(symbol))
    except Exception:
        mark_price = get_price(symbol)

    # compute TP price based on entry/last close (we use current mark price)
    if side.upper() == "BUY":
        tp_price = mark_price * (1.0 + take_profit_pct)
        tp_side = "SELL"
    else:
        tp_price = mark_price * (1.0 - take_profit_pct)
        tp_side = "BUY"

    # format stopPrice as string with correct precision based on tickSize
    s_info = get_symbol_info(symbol)
    tickSize = get_filter_value(s_info, "PRICE_FILTER", "tickSize") or "0.01"
    # round stopPrice to tickSize precision: use math.floor/round appropriately (for TP round to tick)
    tick = float(tickSize)
    precision = max(0, int(round(-math.log10(tick)))) if tick < 1 else 0
    stop_price_str = f"{round(tp_price, precision):.{precision}f}"

    # Place TAKE_PROFIT_MARKET with closePosition=True (will close whole position when triggered)
    try:
        params = {
            "symbol": symbol,
            "side": tp_side,
            "type": "TAKE_PROFIT_MARKET",
            # stopPrice is required for TAKE_PROFIT_MARKET
            "stopPrice": stop_price_str,
            "closePosition": True
        }
        if tp_using_mark_price:
            params["workingType"] = "MARK_PRICE"
        logging.info("Placing TP (TAKE_PROFIT_MARKET): %s", params)
        tp_resp = client.futures_create_order(**params)
        logging.info("TP order placed: %s", tp_resp)
    except BinanceAPIException as e:
        logging.error("TP order failed: %s", e)
        return {"ok": False, "open_resp": open_resp, "error": f"TP order failed: {e.message if hasattr(e,'message') else str(e)}"}
    except Exception as e:
        logging.exception("Unexpected TP order error")
        return {"ok": False, "open_resp": open_resp, "error": str(e)}

    return {
        "ok": True,
        "open_resp": open_resp,
        "tp_resp": tp_resp,
        "tp_price": stop_price_str,
        "mark_price_at_open": mark_price,
        "qty": qty
    }

# ---------------- convenience wrapper using strategy output ----------------
def execute_signal_and_place_tp(signal_dict, usdt=10.0, leverage=3, tp_pct=0.02):
    """
    signal_dict from strategy: must contain keys: 'signal' ('LONG'/'SHORT') and 'entry_price' (optional)
    This wrapper will place the market order and TP.
    """
    if not signal_dict or not signal_dict.get("signal"):
        return {"ok": False, "error": "No signal to execute"}

    symbol = signal_dict.get("symbol", "BTCUSDT")
    sig = signal_dict["signal"]
    side = "BUY" if sig == "LONG" else "SELL"
    result = place_market_and_set_tp(symbol, side, amount_usdt=usdt, leverage=leverage, take_profit_pct=tp_pct)
    return result

# ---------------- example usage ----------------
if __name__ == "__main__":
    # quick manual test (ONLY on testnet or with small amounts)
    res = place_market_and_set_tp("BTCUSDT", side="BUY", amount_usdt=5.0, leverage=3, take_profit_pct=0.02)
    print(res)
