import os
import logging
from load_env import *

# ...existing code...
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

def get_futures_usdt_balance():
    """Trả về dict chứa balance và availableBalance của USDT trong ví Futures."""
    try:
        bal = client.futures_account_balance()
        for b in bal:
            if b.get("asset") == "USDT":
                return {
                    "asset": "USDT",
                    "balance": float(b.get("balance", 0) or 0.0),
                    "availableBalance": float(b.get("availableBalance", 0) or 0.0)
                }
        return {"asset": "USDT", "balance": 0.0, "availableBalance": 0.0}
    except Exception as e:
        logging.exception("Failed to fetch futures USDT balance: %s", e)
        return {"asset": "USDT", "balance": 0.0, "availableBalance": 0.0}
# ...existing code...