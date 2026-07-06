import os
import json
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
client_conf = config.get("client", default_config["client"])

CLIENT_PATH = client_conf.get("terminal_path", default_config["client"]["terminal_path"])
REDIS_CHAN = redis_conf.get("channel", default_config["redis"]["channel"])
CLIENT_GOLD_SYMBOL = client_conf.get("gold_symbol", default_config["client"]["gold_symbol"])
LOT_MULTIPLIER = client_conf.get("lot_multiplier", default_config["client"]["lot_multiplier"])
LOT_MIN = client_conf.get("lot_minimum", default_config["client"]["lot_minimum"])
MAGIC_NUMBER = client_conf.get("magic_number", default_config["client"]["magic_number"])
DEVIATION = client_conf.get("deviation", default_config["client"]["deviation"])

if not mt5.initialize(path=CLIENT_PATH):
    print("Client init failed")
    quit()

redis_url = f"redis://{redis_conf.get('host', 'localhost')}:{redis_conf.get('port', 6379)}/{redis_conf.get('db', 0)}"
r = redis.Redis.from_url(redis_url)
pubsub = r.pubsub()
pubsub.subscribe(REDIS_CHAN)

print("Client Executor Started... Waiting for signals")

# ตัวแปรช่วยจำ: เก็บความสัมพันธ์ตั๋ว [ตั๋ว Master] -> [ตั๋ว Client]
ticket_mapping = {}
MAPPING_FILE = "mappings.json"

def load_mappings():
    global ticket_mapping
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, "r") as f:
                loaded = json.load(f)
                # แปลง Key กลับเป็น Integer
                ticket_mapping = {int(k): int(v) for k, v in loaded.items()}
            print(f"[Client] Loaded ticket mapping from file: {ticket_mapping}")
        except Exception as e:
            print(f"[Client] Failed to load mapping file: {e}")

def save_mappings():
    try:
        with open(MAPPING_FILE, "w") as f:
            json.dump(ticket_mapping, f, indent=4)
    except Exception as e:
        print(f"[Client] Failed to save mapping file: {e}")

# โหลดข้อมูลคู่ตั๋วที่เคยค้างไว้กลับเข้ามาตอนเริ่มต้น
load_mappings()

def clean_and_check_symbol(master_symbol):
    # ตรวจสอบว่าสัญลักษณ์ที่ส่งมาเป็นทองคำใช่ไหม (ไม่ว่าจะต่อท้ายด้วยอะไร)
    if "XAUUSD" in master_symbol.upper():
        return CLIENT_GOLD_SYMBOL
    return None

for message in pubsub.listen():
    if message["type"] == "message":
        data = json.loads(message["data"])
        
        # --- กรณีสั่งเปิดออเดอร์ ---
        if data["action"] == "OPEN":
            target_symbol = clean_and_check_symbol(data["symbol"])
            if not target_symbol:
                continue # ไม่ใช่ทองคำ ข้ามไป
                
            # คำนวณ Lot ตามตัวคูณและขั้นต่ำที่กำหนดใน config
            lot = round(float(data["volume"]) * LOT_MULTIPLIER, 2)
            lot = max(lot, LOT_MIN)

            order_type = mt5.ORDER_TYPE_BUY if data["type"] == 0 else mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(target_symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(target_symbol).bid

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": target_symbol,
                "volume": lot,
                "type": order_type,
                "price": price,
                "deviation": DEVIATION,
                "magic": MAGIC_NUMBER,
                "comment": f"Copy Master {data['master_ticket']}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                # บันทึกคู่ตั๋วไว้ เวลาปิดจะได้ตามไปปิดถูกตัว
                ticket_mapping[data["master_ticket"]] = result.order
                save_mappings()
                print(f"[Client] Copied Open Success (Lot: {lot}). Client Ticket: {result.order}")
            else:
                print(f"[Client] Open Order Failed: {result.comment}")

        # --- กรณีสั่งปิดออเดอร์ (รองรับการสั่งปิดแบบรวดเดียว) ---
        elif data["action"] == "CLOSE":
            master_ticket = data["master_ticket"]
            
            # เช็คว่าเรามีตั๋ว Client ที่ผูกกับตั๋ว Master นี้ไหม
            if master_ticket in ticket_mapping:
                client_ticket = ticket_mapping[master_ticket]
                
                # ตรวจสอบสถานะตั๋ว Client ปัจจุบันก่อนสั่งปิด
                client_pos = mt5.positions_get(ticket=client_ticket)
                if client_pos:
                    pos = client_pos[0]
                    close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
                    close_price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(pos.symbol).ask
                    
                    close_request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": pos.symbol,
                        "volume": pos.volume, # ปิดตาม Volume จริงที่มีอยู่
                        "type": close_type,
                        "position": client_ticket,
                        "price": close_price,
                        "deviation": DEVIATION,
                        "magic": MAGIC_NUMBER,
                        "comment": f"Close Copy {master_ticket}",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    
                    close_result = mt5.order_send(close_request)
                    if close_result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"[Client] Closed Ticket {client_ticket} (Master {master_ticket})")
                        del ticket_mapping[master_ticket] # ลบข้อมูลคู่ออกเมื่อปิดสำเร็จ
                        save_mappings()
                    else:
                        print(f"[Client] Close Failed for Ticket {client_ticket}: {close_result.comment}")
                else:
                    # ตั๋วในฝั่ง Client อาจจะปิดไปก่อนหน้านี้แล้ว (เช่น ชน TP/SL ฝั่งตัวเอง)
                    del ticket_mapping[master_ticket]
                    save_mappings()