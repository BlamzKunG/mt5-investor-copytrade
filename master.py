import os
import json
import time
import MetaTrader5 as mt5
import redis

CONFIG_FILE = "config.json"

# ค่าคอนฟิกเริ่มต้น (Default Configuration)
default_config = {
    "redis": {
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "channel": "copy_trade_gold"
    },
    "master": {
        "terminal_path": r"C:\Program Files\MetaTrader 5 - Copy (2)\terminal64.exe",
        "poll_interval_seconds": 0.05
    },
    "client": {
        "terminal_path": r"C:\Program Files\MetaTrader 5\terminal64.exe",
        "gold_symbol": "XAUUSD-ECN",
        "lot_multiplier": 0.5,
        "lot_minimum": 0.01,
        "magic_number": 999999,
        "deviation": 20
    }
}

# โหลดคอนฟิกจากไฟล์ json
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)
    print(f"Created default configuration file: {CONFIG_FILE}")

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

# ดึงค่าคอนฟิกไปใช้งาน
redis_conf = config.get("redis", default_config["redis"])
master_conf = config.get("master", default_config["master"])

MASTER_PATH = master_conf.get("terminal_path", default_config["master"]["terminal_path"])
REDIS_CHAN = redis_conf.get("channel", default_config["redis"]["channel"])
POLL_INTERVAL = master_conf.get("poll_interval_seconds", default_config["master"]["poll_interval_seconds"])

r = redis.Redis(
    host=redis_conf.get("host", "localhost"),
    port=redis_conf.get("port", 6379),
    db=redis_conf.get("db", 0)
)

if not mt5.initialize(path=MASTER_PATH):
    print("Master init failed")
    quit()

print("Master Reader Started... Monitoring Investor Account")

last_positions = {}

while True:
    # ดึงออเดอร์ที่เปิดอยู่ทั้งหมดของทองคำ (กรองเฉพาะทองคำ หรือดูทั้งหมดก็ได้)
    # ในที่นี้ขอดึงทั้งหมด แล้วค่อยไปคัดกรองสัญลักษณ์เอา
    positions = mt5.positions_get()
    
    if positions is None:
        time.sleep(POLL_INTERVAL)
        continue

    current_positions = {p.ticket: p for p in positions}

    # 1. ตรวจสอบออเดอร์เปิดใหม่ (New Position)
    for ticket, pos in current_positions.items():
        if ticket not in last_positions:
            # ตรวจเจอออเดอร์ใหม่! ส่งข้อมูลไปให้ Client
            trade_data = {
                "action": "OPEN",
                "master_ticket": pos.ticket,
                "symbol": pos.symbol, # ส่งชื่อเต็มไป (เช่น XAUUSD. หรือ XAUUSD-ECN)
                "type": pos.type,     # 0 = Buy, 1 = Sell
                "volume": pos.volume  # ดึงค่า Lot ออกมาตรงๆ ตามต้องการ
            }
            r.publish(REDIS_CHAN, json.dumps(trade_data))
            print(f"[Master] Detected New Open: {trade_data}")

    # 2. ตรวจสอบออเดอร์ที่ถูกปิด (รวมถึงการปิดรวบ Bulk Close)
    for ticket, pos in last_positions.items():
        if ticket not in current_positions:
            # ตั๋วนี้หายไปจากพอร์ต แปลว่าถูกปิดแล้ว
            trade_data = {
                "action": "CLOSE",
                "master_ticket": pos.ticket
            }
            r.publish(REDIS_CHAN, json.dumps(trade_data))
            print(f"[Master] Detected Close: Ticket {ticket}")

    last_positions = current_positions
    time.sleep(POLL_INTERVAL) # หน่วงเวลาตามที่กำหนดใน config เพื่อไม่ให้ CPU ทำงานหนักเกินไป