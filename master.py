import json
import time
import MetaTrader5 as mt5
import redis

# ตั้งค่าทางเดินโปรแกรมตามที่ระบุ
MASTER_PATH = r"C:\Program Files\MetaTrader 5 - Copy (2)\terminal64.exe"
REDIS_CHAN = "copy_trade_gold"

r = redis.Redis(host="localhost", port=6379, db=0)

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
        time.sleep(0.05)
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
    time.sleep(0.05) # หน่วงเวลา 50ms เพื่อไม่ให้ CPU ทำงานหนักเกินไป