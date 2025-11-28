# position_utils.py
from binance.client import Client
from binance.exceptions import BinanceAPIException
import os
from load_env import *
from order import client
import logging

def fetch_all_orders_for_symbol(symbol, limit=100):
    """Lấy lịch sử (tất cả) order cho symbol, bao gồm đã fill."""
    try:
        orders = client.futures_get_all_orders(symbol=symbol, limit=limit)
        return {"ok": True, "orders": orders}
    except Exception as e:
        logging.exception("Failed to fetch all orders for %s: %s", symbol, e)
        return {"ok": False, "error": str(e)}

def get_last_order(symbol):
    """Trả về order mới nhất (theo updateTime/time) cho symbol, hoặc None nếu không có."""
    res = fetch_all_orders_for_symbol(symbol, limit=200)
    if not res.get("ok"):
        return res
    orders = res.get("orders", [])
    if not orders:
        return {"ok": True, "order": None}
    orders_sorted = sorted(orders, key=lambda o: o.get("updateTime", o.get("time", 0)), reverse=True)
    return {"ok": True, "order": orders_sorted[0]}

def check_open_orders(symbol=None):
    """
    Kiểm tra các lệnh Futures đang mở (open orders)
    - symbol: nếu None thì lấy tất cả, nếu có thì chỉ lấy 1 cặp
    Trả về: list các lệnh đang mở, hoặc []
    """
    try:
        if symbol:
            orders = client.futures_get_open_orders(symbol=symbol)
        else:
            orders = client.futures_get_open_orders()
        if not orders:
            print("✅ Không có lệnh nào đang mở.")
            return []
        print(f"✅ Có {len(orders)} lệnh đang mở:")
        for o in orders:
            print(f"  • {o['symbol']} | {o['side']} {o['origQty']} @ {o.get('price')} | status={o['status']}")
        return orders
    except BinanceAPIException as e:
        print(f"❌ Binance API Error: {e.message}")
        return []
    except Exception as e:
        print(f"❌ Lỗi không xác định: {e}")
        return []


def get_position_pnl(symbol: str):
    """
    Check if there's an open futures position for `symbol`.
    If yes, return dict with:
      - positionAmt (float): positive = long, negative = short
      - entryPrice (float)
      - markPrice (float)
      - unRealizedProfit (float)  # in USDT
      - pnl_percent (float)       # percentage relative to entry (signed)
      - notional (float)          # abs(positionAmt) * markPrice
      - leverage (int)
      - raw position dict (position_info)
    If no open position (positionAmt == 0), returns ok with positionAmt == 0.
    """
    try:
        positions = client.futures_position_information(symbol=symbol)
        if not positions:
            return {"ok": True, "has_position": False, "msg": "No position info returned"}
        # positions is a list — usually one element for given symbol
        p = positions[0]
        pos_amt = float(p.get("positionAmt", 0))
        entry_price = float(p.get("entryPrice", 0) or 0)
        unrealized = float(p.get("unRealizedProfit", 0) or 0)
        leverage = int(p.get("leverage", 1) or 1)

        if pos_amt == 0:
            return {"ok": True, "has_position": False, "positionAmt": 0}

        # get mark price
        mark = client.futures_mark_price(symbol=symbol)
        mark_price = float(mark.get("markPrice", mark.get("price", 0)) or 0)

        # notional (current value) and invested (approx)
        notional = abs(pos_amt) * mark_price
        invested = abs(pos_amt) * entry_price if entry_price > 0 else 0.0

        # compute pnl percent relative to entryPrice (signed)
        # For long: (mark - entry) / entry * 100
        # For short: (entry - mark) / entry * 100  -> same formula if we multiply by sign
        sign = 1 if pos_amt > 0 else -1
        pnl_percent = 0.0
        if entry_price > 0:
            pnl_percent = ((mark_price - entry_price) / entry_price) * 100 * sign

        result = {
            "ok": True,
            "has_position": True,
            "symbol": symbol,
            "positionAmt": pos_amt,
            "entryPrice": entry_price,
            "markPrice": mark_price,
            "unRealizedProfit": unrealized,
            "pnl_percent": pnl_percent,
            "notional": notional,
            "invested": invested,
            "leverage": leverage,
            "raw": p
        }
        return result

    except BinanceAPIException as e:
        return {"ok": False, "error": f"BinanceAPIException: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_open_positions():
    """
    Trả về danh sách các position đang mở (positionAmt != 0) trên Futures.
    Kết quả:
      {
        "ok": True/False,
        "count": <số position mở>,
        "positions": [
          {
            "symbol": "ETHUSDT",
            "positionAmt": float,
            "positionSide": str,
            "entryPrice": float,
            "markPrice": float,
            "unRealizedProfit": float,
            "leverage": int,
            "notional": float,           # approx = abs(positionAmt) * markPrice
            "isolated": bool,
            "raw": <original position dict from Binance>
          }, ...
        ],
        "error": <message if ok==False>
      }
    """
    try:
        positions = client.futures_position_information()
        res = []
        for p in positions:
            try:
                amt = float(p.get("positionAmt", 0) or 0.0)
            except Exception:
                amt = 0.0
            if amt == 0.0:
                continue
            try:
                mark = float(p.get("markPrice", 0) or 0.0)
            except Exception:
                mark = 0.0
            try:
                entry = float(p.get("entryPrice", 0) or 0.0)
            except Exception:
                entry = 0.0
            try:
                unreal = float(p.get("unRealizedProfit", 0) or 0.0)
            except Exception:
                unreal = 0.0

            notional = abs(amt) * mark if mark else None

            res.append({
                "symbol": p.get("symbol"),
                "positionAmt": amt,
                "positionSide": p.get("positionSide"),  # e.g. BOTH / LONG/SHORT depending on mode
                "entryPrice": entry,
                "markPrice": mark,
                "unRealizedProfit": unreal,
                "leverage": int(p.get("leverage", 0) or 0),
                "notional": notional,
                "isolated": p.get("isolated") == "TRUE" or p.get("marginType") == "ISOLATED",
                "raw": p
            })

        return {"ok": True, "count": len(res), "positions": res}
    except Exception as e:
        logging.exception("Failed to fetch futures positions: %s", e)
        return {"ok": False, "error": str(e)}

def get_open_position_by_symbol(symbol):
    """
    Trả về position mở cho `symbol` hoặc {'ok': True, 'position': None} nếu không có.
    """
    all_pos = get_open_positions()
    if not all_pos.get("ok"):
        return all_pos
    for p in all_pos["positions"]:
        if p["symbol"] == symbol:
            return {"ok": True, "position": p}
    return {"ok": True, "position": None}
