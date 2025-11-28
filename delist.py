from dotenv import load_dotenv
import os
from binance.client import Client
from pprint import pprint
import pandas as pd
import datetime

# --- CONFIG ---
OUT_CSV = "delist.csv"

# Create client for public endpoints (no API key required)
# client = Client()

# VN timezone (UTC+7)
TZ_VN = datetime.timezone(datetime.timedelta(hours=7))

def ms_to_dt(ms, tz=TZ_VN):
    """Convert epoch ms to timezone-aware datetime. Return None if invalid."""
    if not ms:
        return None
    try:
        return datetime.datetime.fromtimestamp(int(ms) / 1000, tz)
    except Exception:
        return None

def is_placeholder_2100(dt):
    """Detect placeholder 2100-12-25 (year==2100)."""
    if dt is None:
        return False
    return dt.year == 2100

def get_delist():
    # Lấy exchange info cho USDⓈ-M Futures
    info = client.futures_exchange_info()
    symbols = info.get("symbols", [])

    now_vn = datetime.datetime.now(TZ_VN)

    records = []
    for s in symbols:
        status = s.get("status", "")
        # Chỉ quan tâm những cặp khác TRADING (đã dừng/delisted/settle...)
        if status == "TRADING":
            continue

        delivery_ms = s.get("deliveryDate")
        delivery_dt_vn = ms_to_dt(delivery_ms, TZ_VN)

        # Bỏ những cặp không có deliveryDate hoặc deliveryDate là placeholder (2100)
        if delivery_dt_vn is None:
            continue
        if is_placeholder_2100(delivery_dt_vn):
            continue

        # Chỉ giữ những cặp có deliveryDate > now (tức scheduled after today VN time)
        if not (delivery_dt_vn > now_vn):
            # nếu delivery trước hoặc bằng thời điểm hiện tại thì bỏ qua
            continue

        records.append({
            "symbol": s.get("symbol"),
            "pair": f"{s.get('baseAsset')}/{s.get('quoteAsset')}",
            "status": status,
            "contractType": s.get("contractType"),
            "deliveryDate_ms": delivery_ms,
            "deliveryDate_vn": delivery_dt_vn.isoformat(),
        })

    # Lưu CSV
    df = pd.DataFrame(records)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print(f"Done. Đã lưu {len(df)} cặp vào '{OUT_CSV}'. (timezone GMT+7)")
    if len(df) > 0:
        print(df.head())

# if __name__ == "__main__":
#     main()