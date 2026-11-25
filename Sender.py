import select
import sys
import time
from time import sleep
from machine import UART, Pin
import urequests
import gc

# =========================================================
# FIREBASE & HARDWARE CONFIG
# =========================================================
FIREBASE_BASE_URL = "https://miniproject-iot-b4b80-default-rtdb.asia-southeast1.firebasedatabase.app/iot_control"
CMD_URL = f"{FIREBASE_BASE_URL}/command.json"
RESPONSE_URL = f"{FIREBASE_BASE_URL}/response.json"

uart2 = UART(2, baudrate=9600, tx=Pin(17), rx=Pin(16))
uart2.init(9600, bits=8, parity=None, stop=1)

state = 0
last_firebase_check = time.ticks_ms()
state_1_start_time = 0

cli_step = 0
selected_func = ""
NO_VALUE_FUNCS = ["3", "4", "5", "7", "10", "13"]


def print_terminal_menu():
    """พิมพ์รายการเมนูทั้ง 13 ฟังก์ชัน"""
    print("\n" + "=" * 55)
    print("      IoT Device Control Panel (Terminal CLI)")
    print("=" * 55)
    print(" [1]  Set Time           -> ป้อน: 1,hh,mm,ss")
    print(" [2]  Set Motor Speed    -> ป้อน: 2,speed (0-100)")
    print(" [3]  Read Current Lux   -> ป้อน: 3")
    print(" [4]  Timer OFF          -> ป้อน: 4")
    print(" [5]  Timer ON           -> ป้อน: 5")
    print(" [6]  Set Lux Range      -> ป้อน: 6,min,max")
    print(" [7]  Read Lux Range     -> ป้อน: 7")
    print(" [8]  Set Start Time 1   -> ป้อน: 8,hh,mm,ss")
    print(" [9]  Set Stop Time 1    -> ป้อน: 9,hh,mm,ss")
    print(" [10] Read Timer 1       -> ป้อน: 10")
    print(" [11] Set Start Time 2   -> ป้อน: 11,hh,mm,ss")
    print(" [12] Set Stop Time 2    -> ป้อน: 12,hh,mm,ss")
    print(" [13] Read Timer 2       -> ป้อน: 13")
    print("-" * 55)
    print("พิมพ์คำสั่งที่ต้องการ แล้วกด Enter:")
    print("> ", end="")

def clean_string(raw_str):
    cleaned = ""
    for ch in str(raw_str):
        if 32 <= ord(ch) <= 126:
            cleaned += ch
    return (
        cleaned.replace('"', "")
        .replace("'", "")
        .replace("\\r", "")
        .replace("\\n", "")
        .strip()
    )


def get_firebase_command():
    res = None
    try:
        gc.collect()
        res = urequests.get(CMD_URL)
        if res.status_code == 200:
            data = res.json()
            if data and data != "":
                cleaned = clean_string(data)
                return cleaned
    except Exception as e:
        print("[Sender] Get Firebase Error:", e)
    finally:
        if res:
            res.close()
    return ""


def clear_firebase_command():
    res = None
    try:
        headers = {'Content-Type': 'application/json'}
        res = urequests.put(CMD_URL, data='""', headers=headers)
        if res.status_code == 200:
            print("[Sender] Cleared Firebase command successfully")
        else:
            print(f"[Sender] Clear Failed Status: {res.status_code}")
    except Exception as e:
        print("[Sender] Clear Command Error:", e)
    finally:
        if res:
            res.close()


def send_firebase_response(msg):
    res = None
    try:
        headers = {'Content-Type': 'application/json'}
        clean_msg = clean_string(msg)
        # ส่ง string เป็น JSON โดยใส่เครื่องหมายคำพูดครอบ
        payload = f'"{clean_msg}"'
        res = urequests.put(RESPONSE_URL, data=payload, headers=headers)
        print(f"[Sender] Updated Firebase Response: '{clean_msg}'")
    except Exception as e:
        print("[Sender] Firebase Response Error:", e)
    finally:
        if res:
            res.close()


def send_uart_cmd(cmd_text):
    global state, state_1_start_time
    clean_cmd = clean_string(cmd_text)

    if not clean_cmd:
        return

    send_pkt = clean_cmd if clean_cmd.endswith("#") else clean_cmd + "#"
    print(f"\n[Sender Command] -> Sending UART: '{send_pkt}'")
    uart2.write(send_pkt.encode("utf-8"))
    state = 1
    state_1_start_time = time.ticks_ms()


# Terminal Listener
poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)

sleep(0.5)
print("=== ESP32 Sender Gateway Ready ===")
print_terminal_menu()

while True:
    # 1. ระบบรับคำสั่งพิมพ์ผ่าน Terminal CLI
    poll_results = poll_obj.poll(0)
    if poll_results:
        line = sys.stdin.readline()
        if line is not None:
            input_val = clean_string(line)

            if cli_step == 2:
                cli_step = 0
                print_terminal_menu()
            elif input_val:
                send_uart_cmd(input_val)

    # 2. เช็กคำสั่งจาก Firebase ทุกๆ 1 วินาที (เมื่ออยู่ในสถานะพร้อม state == 0)
    if state == 0:
        if time.ticks_diff(time.ticks_ms(), last_firebase_check) >= 1000:
            last_firebase_check = time.ticks_ms()
            fb_cmd = get_firebase_command()

            if fb_cmd and fb_cmd != "":
                print(f"\n[Firebase Cmd Received]: '{fb_cmd}'")
                clear_firebase_command()
                send_uart_cmd(fb_cmd)

    # 3. รอรับผลตอบกลับจาก Receiver ทาง UART (สถานะ state == 1)
    elif state == 1:
        if uart2.any():
            sleep(0.1)
            try:
                data_bytes = uart2.read()
                if data_bytes:
                    return_message = clean_string(data_bytes.decode("utf-8", "ignore"))
                    print("Return message from Receiver:", return_message)
                    send_firebase_response(return_message)
            except Exception as e:
                print("UART Read Error:", e)

            state = 0
            cli_step = 2
            print("\n>> กด [Enter] เพื่อแสดงเมนูอีกครั้ง...")

        elif time.ticks_diff(time.ticks_ms(), state_1_start_time) > 3000:
            print("[Sender] UART Response Timeout -> Reset State")
            state = 0
            cli_step = 2
            print("\n>> กด [Enter] เพื่อแสดงเมนูอีกครั้ง...")

    sleep(0.02)