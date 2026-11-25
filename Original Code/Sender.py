import select
import sys
import time
from time import sleep
from machine import UART, Pin
import urequests

# =========================================================
# FIREBASE & HARDWARE CONFIG
# =========================================================
FIREBASE_BASE_URL = "https://miniproject-iot-b4b80-default-rtdb.asia-southeast1.firebasedatabase.app/iot_control"
CMD_URL = f"{FIREBASE_BASE_URL}/command.json"
RESPONSE_URL = f"{FIREBASE_BASE_URL}/response.json"

uart2 = UART(2, baudrate=9600, tx=Pin(17), rx=Pin(16))
uart2.init(9600, bits=8, parity=None, stop=1)

state = 0
last_firebase_check = 0
state_1_start_time = 0

cli_step = 0        # 0: เลือกฟังก์ชัน, 1: ป้อนค่า, 2: รอ Enter เพื่อโชว์เมนู
selected_func = ""
NO_VALUE_FUNCS = ["3", "4", "5", "7", "10", "13"]


def print_terminal_menu():
  """พิมพ์รายการเมนูทั้ง 13 ฟังก์ชัน"""
  print("\n" + "=" * 55)
  print("      IoT Device Control Panel (Terminal CLI)")
  print("=" * 55)
  print(" [1] Set Time           -> ค่าที่ต้องป้อน: hh,mm,ss")
  print(" [2] Set Motor Speed    -> ค่าที่ต้องป้อน: speed (0-100)")
  print(" [3] Read Current Lux   -> (ทำงานทันที)")
  print(" [4] Timer OFF          -> (ทำงานทันที)")
  print(" [5] Timer ON           -> (ทำงานทันที)")
  print(" [6] Set Lux Range      -> ค่าที่ต้องป้อน: min,max")
  print(" [7] Read Lux Range     -> (ทำงานทันที)")
  print(" [8] Set Start Time 1   -> ค่าที่ต้องป้อน: hh,mm,ss")
  print(" [9] Set Stop Time 1    -> ค่าที่ต้องป้อน: hh,mm,ss")
  print(" [10] Read Timer 1      -> (ทำงานทันที)")
  print(" [11] Set Start Time 2  -> ค่าที่ต้องป้อน: hh,mm,ss")
  print(" [12] Set Stop Time 2   -> ค่าที่ต้องป้อน: hh,mm,ss")
  print(" [13] Read Timer 2      -> (ทำงานทันที)")
  print("-" * 55)
  print("เลือกฟังก์ชันการทำงาน (พิมพ์เลข 1 - 13 ในบรรทัดล่างสุด):")
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
  try:
    res = urequests.get(CMD_URL)
    if res.status_code == 200:
      data = res.json()
      res.close()
      if data:
        return clean_string(data)
  except Exception as e:
    pass
  return ""


def clear_firebase_command():
  try:
    res = urequests.put(CMD_URL, json="")
    res.close()
  except:
    pass


def send_firebase_response(msg):
  try:
    res = urequests.put(RESPONSE_URL, json=msg)
    res.close()
    print(f"[Sender] Updated Firebase Response: '{msg}'")
  except Exception as e:
    print("[Sender] Firebase Response Error:", e)


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


# Non-blocking Terminal Listener
poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)

sleep(0.5)
print("=== ESP32 Sender Gateway Ready ===")
print_terminal_menu()

while True:
  # 1. ระบบรับคำสั่งพิมพ์ผ่าน Terminal
  poll_results = poll_obj.poll(0)
  if poll_results:
    line = sys.stdin.readline()
    if line is not None:
      input_val = clean_string(line)

      # ขั้นตอนที่ 2: รอกด Enter เพื่อแสดงเมนูอีกครั้ง
      if cli_step == 2:
        cli_step = 0
        print_terminal_menu()

      elif input_val:
        # ขั้นตอนที่ 0: เลือกเลขฟังก์ชัน
        if cli_step == 0:
          selected_func = input_val

          if selected_func in NO_VALUE_FUNCS:
            full_cmd = selected_func + "#"
            send_uart_cmd(full_cmd)
          else:
            cli_step = 1
            print(
                f"\nป้อนค่าสำหรับฟังก์ชัน [{selected_func}]"
                " (พิมพ์ค่าแล้วกด Enter):"
            )
            print("> ", end="")

        # ขั้นตอนที่ 1: ป้อนค่า Value
        elif cli_step == 1:
          val = input_val
          full_cmd = f"{selected_func},{val}#"
          send_uart_cmd(full_cmd)

  # 2. เช็กคำสั่งจาก Firebase / Web
  if state == 0:
    if time.ticks_ms() - last_firebase_check > 1000:
      last_firebase_check = time.ticks_ms()
      fb_cmd = get_firebase_command()

      if fb_cmd and fb_cmd != "":
        print(f"\n[Firebase Cmd Received]: '{fb_cmd}'")
        clear_firebase_command()
        send_uart_cmd(fb_cmd)

  # 3. รอรับผลตอบกลับจาก Receiver แล้วรอสั่งกด Enter
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
      cli_step = 2  # เปลี่ยนสถานะเป็นรอกด Enter
      print("\n>> กด [Enter] เพื่อแสดงเมนูอีกครั้ง...")

    elif time.ticks_diff(time.ticks_ms(), state_1_start_time) > 3000:
      print("[Sender] UART Response Timeout -> Reset State")
      state = 0
      cli_step = 2
      print("\n>> กด [Enter] เพื่อแสดงเมนูอีกครั้ง...")

  sleep(0.02)