import json
import MetaTrader5 as mt5
import redis

CLIENT_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
REDIS_CHAN = "copy_trade_gold"

# กำหนดชื่อทองคำของฝั่ง Client ที่ต้องการให้เทรดจริง เช่น "XAUUSD" หรือ "XAUUSD-ECN"
CLIENT_GOLD_SYMBOL = "XAUUSD-ECN" 

if not mt5.initialize(path=CLIENT_PATH):
    print("Client init failed")
    quit()

r = redis.Redis.from_url("redis://localhost:6379/0")
pubsub = r.pubsub()
pubsub.subscribe(REDIS_CHAN)

print("Client Executor Started... Waiting for signals")

# ตัวแปรช่วยจำ: เก็บความสัมพันธ์ตั๋ว [ตั๋ว Master] -> [ตั๋ว Client]
ticket_mapping = {}

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
                
            # รับค่า Lot มาแล้วหาร 2 ปัดเศษ 2 ตำแหน่ง และป้องกันไม่ให้ต่ำกว่า 0.01
            lot = round(float(data["volume"]) / 2, 2)
            lot = max(lot, 0.01)

            order_type = mt5.ORDER_TYPE_BUY if data["type"] == 0 else mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(target_symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(target_symbol).bid

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": target_symbol,
                "volume": lot,
                "type": order_type,
                "price": price,
                "deviation": 20,
                "magic": 999999,
                "comment": f"Copy Master {data['master_ticket']}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                # บันทึกคู่ตั๋วไว้ เวลาปิดจะได้ตามไปปิดถูกตัว
                ticket_mapping[data["master_ticket"]] = result.order
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
                        "deviation": 20,
                        "magic": 999999,
                        "comment": f"Close Copy {master_ticket}",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    
                    close_result = mt5.order_send(close_request)
                    if close_result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"[Client] Closed Ticket {client_ticket} (Master {master_ticket})")
                        del ticket_mapping[master_ticket] # ลบข้อมูลคู่ออกเมื่อปิดสำเร็จ
                    else:
                        print(f"[Client] Close Failed for Ticket {client_ticket}: {close_result.comment}")
                else:
                    # ตั๋วในฝั่ง Client อาจจะปิดไปก่อนหน้านี้แล้ว (เช่น ชน TP/SL ฝั่งตัวเอง)
                    del ticket_mapping[master_ticket]