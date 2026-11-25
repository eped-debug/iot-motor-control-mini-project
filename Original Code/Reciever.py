import json
import select
import sys
import time
import machine
from machine import I2C, PWM, UART, Pin

# =========================================================
# 1. HARDWARE INITIALIZATION
# =========================================================
uart2 = UART(2, baudrate=9600, tx=Pin(17), rx=Pin(16))
uart2.init(9600, bits=8, parity=None, stop=1)

i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)


class I2cLcd:

  def __init__(self, i2c, addr=0x27):
    self.i2c = i2c
    self.addr = addr
    self.backlight = 0x08
    time.sleep_ms(20)
    for cmd in [0x03, 0x03, 0x03, 0x02, 0x28, 0x0C, 0x06, 0x01]:
      self._write_cmd(cmd)

  def _write_byte(self, data):
    try:
      self.i2c.writeto(self.addr, bytes([data | self.backlight]))
    except:
      pass

  def _toggle_enable(self, data):
    self._write_byte(data | 0x04)
    time.sleep_us(1)
    self._write_byte(data & ~0x04)
    time.sleep_us(50)

  def _write_cmd(self, cmd):
    self._write_byte(cmd & 0xF0)
    self._toggle_enable(cmd & 0xF0)
    self._write_byte((cmd << 4) & 0xF0)
    self._toggle_enable((cmd << 4) & 0xF0)

  def _write_data(self, data):
    self._write_byte((data & 0xF0) | 0x01)
    self._toggle_enable((data & 0xF0) | 0x01)
    self._write_byte(((data << 4) & 0xF0) | 0x01)
    self._toggle_enable(((data << 4) & 0xF0) | 0x01)

  def clear(self):
    self._write_cmd(0x01)
    time.sleep_ms(2)

  def move_to(self, col, row):
    self._write_cmd(0x80 | (col + (0x40 if row else 0x00)))

  def putstr(self, string):
    for char in string:
      self._write_data(ord(char))


class BH1750:

  def __init__(self, i2c, addr=0x23):
    self.i2c = i2c
    self.addr = addr
    try:
      self.i2c.writeto(self.addr, b'\x10')
    except:
      pass

  def read_lux(self):
    try:
      d = self.i2c.readfrom(self.addr, 2)
      lux = ((d[0] << 8) | d[1]) / 1.2
      return round(lux, 1)
    except Exception as e:
      try:
        self.i2c.writeto(self.addr, b'\x10')
      except:
        pass
      return 0.0


class DS3231:

  def __init__(self, i2c, addr=0x68):
    self.i2c, self.addr = i2c, addr

  def _bcd2dec(self, bcd):
    return (bcd // 16 * 10) + (bcd % 16)

  def _dec2bcd(self, dec):
    return (dec // 10 * 16) + (dec % 10)

  def get_time_tuple(self):
    try:
      d = self.i2c.readfrom_mem(self.addr, 0x00, 3)
      hh = self._bcd2dec(d[2] & 0x3F)
      mm = self._bcd2dec(d[1] & 0x7F)
      ss = self._bcd2dec(d[0] & 0x7F)
      return hh, mm, ss
    except:
      return 0, 0, 0

  def set_time(self, hh, mm, ss=0):
    try:
      self.i2c.writeto_mem(
          self.addr,
          0x00,
          bytearray([self._dec2bcd(ss), self._dec2bcd(mm), self._dec2bcd(hh)]),
      )
      return True
    except:
      return False


lcd_addr = 0x27
try:
  devices = i2c.scan()
  if 0x3F in devices:
    lcd_addr = 0x3F
  elif 0x27 in devices:
    lcd_addr = 0x27
except:
  pass

bh = BH1750(i2c)
rtc = DS3231(i2c)
lcd = I2cLcd(i2c, addr=lcd_addr)

# DC Motor Pins Setup
pin_en = Pin(5, Pin.OUT)
pwm_motor = PWM(pin_en, freq=1000)
pin_in1 = Pin(4, Pin.OUT)
pin_in2 = Pin(2, Pin.OUT)

# Keypad Pins Setup (Cols: 26, 27, 12, 14 | Rows: 25, 33, 32, 18)
cols = [Pin(26, Pin.OUT), Pin(27, Pin.OUT), Pin(12, Pin.OUT), Pin(14, Pin.OUT)]
for c in cols:
  c.value(1)

rows = [
    Pin(25, Pin.IN, Pin.PULL_UP),
    Pin(33, Pin.IN, Pin.PULL_UP),
    Pin(32, Pin.IN, Pin.PULL_UP),
    Pin(18, Pin.IN, Pin.PULL_UP),
]

KEY_MAP = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D'],
]

config = {
    "dev_state": True,
    "motor_speed": 80,
    "timer_active": False,
    "lux_min": 10.0,
    "lux_max": 1000.0,
    "t1_start": "00:00:00",
    "t1_stop": "00:00:00",
    "t2_start": "00:00:00",
    "t2_stop": "00:00:00",
}


def load_config():
  global config
  try:
    with open("config.json", "r") as f:
      config = json.load(f)
      config["lux_min"] = float(config.get("lux_min", 10.0))
      config["lux_max"] = float(config.get("lux_max", 1000.0))
  except:
    save_config()


def save_config():
  try:
    with open("config.json", "w") as f:
      json.dump(config, f)
  except:
    pass


current_motor_pwm = -1


def apply_motor_hardware_pwm(spd):
  global current_motor_pwm
  spd = max(0, min(100, int(spd)))

  if spd != current_motor_pwm:
    current_motor_pwm = spd
    if spd == 0 or not config.get("dev_state", True):
      pin_in1.value(0)
      pin_in2.value(0)
      pwm_motor.duty(0)
    else:
      pin_in1.value(1)
      pin_in2.value(0)
      pwm_motor.duty(int((spd / 100.0) * 1023))


lcd_hold_until = 0


def show_temp_message(line1, line2="", hold_sec=2):
  """โชว์ข้อความป๊อปอัปแจ้งสถานะ 2 วินาที แล้วตั้งเวลาเตรียมคืนสู่หน้าหลัก"""
  global lcd_hold_until
  lcd.clear()
  lcd.move_to(0, 0)
  lcd.putstr(line1[:16])
  if line2:
    lcd.move_to(0, 1)
    lcd.putstr(line2[:16])
  lcd_hold_until = time.ticks_add(time.ticks_ms(), int(hold_sec * 1000))


def time_to_seconds(t_str):
  try:
    parts = str(t_str).replace(",", ":").strip().split(":")
    return (
        (int(parts[0]) * 3600)
        + (int(parts[1]) * 60)
        + (int(parts[2]) if len(parts) > 2 else 0)
    )
  except:
    return 0


def parse_time_str(t_str):
  parts = str(t_str).replace(",", ":").strip().split(":")
  hh = int(parts[0]) if len(parts) > 0 else 0
  mm = int(parts[1]) if len(parts) > 1 else 0
  ss = int(parts[2]) if len(parts) > 2 else 0
  return hh, mm, ss, f"{hh:02d}:{mm:02d}:{ss:02d}"


def is_time_in_range(start_str, stop_str, current_sec):
  start_sec = time_to_seconds(start_str)
  stop_sec = time_to_seconds(stop_str)

  if start_sec == stop_sec:
    return False

  if start_sec < stop_sec:
    return start_sec <= current_sec < stop_sec
  else:
    return current_sec >= start_sec or current_sec < stop_sec


def print_terminal_menu():
  """พิมพ์รายการเมนูทั้ง 13 ฟังก์ชันออกทาง Thonny Shell Terminal"""
  print("\n" + "=" * 50)
  print("      IoT Device Control Panel (Terminal CLI)")
  print("=" * 50)
  print(" [1] Set Time           -> Format: 1,hh,mm,ss")
  print(" [2] Set Motor Speed    -> Format: 2,speed(0-100)")
  print(" [3] Read Current Lux   -> Format: 3")
  print(" [4] Timer OFF          -> Format: 4")
  print(" [5] Timer ON           -> Format: 5")
  print(" [6] Set Lux Range      -> Format: 6,min,max")
  print(" [7] Read Lux Range     -> Format: 7")
  print(" [8] Set Start Time 1   -> Format: 8,hh,mm,ss")
  print(" [9] Set Stop Time 1    -> Format: 9,hh,mm,ss")
  print(" [10] Read Timer 1      -> Format: 10")
  print(" [11] Set Start Time 2  -> Format: 11,hh,mm,ss")
  print(" [12] Set Stop Time 2   -> Format: 12,hh,mm,ss")
  print(" [13] Read Timer 2      -> Format: 13")
  print("-" * 50)
  print(" พิมพ์คำสั่งแล้วกด Enter (หรือพิมพ์ 'menu' เพื่อดูเมนูอีกครั้ง):")
  print("=" * 50 + "\n")


def clean_string(raw_str):
  cleaned = ""
  for ch in str(raw_str):
    if 32 <= ord(ch) <= 126:
      cleaned += ch
  return (
      cleaned.replace('"', "")
      .replace("'", "")
      .replace("#", "")
      .replace("\\r", "")
      .replace("\\n", "")
      .strip()
  )


def execute_command(cmd_str):
  clean_cmd = clean_string(cmd_str)

  if clean_cmd.lower() in ["menu", "help"]:
    print_terminal_menu()
    return "MENU DISPLAYED"

  parts = clean_cmd.split(",")
  func = parts[0].strip()
  res = "OK"

  if func == "1" and len(parts) > 1:
    hh, mm, ss, formatted_full = parse_time_str(",".join(parts[1:]))
    rtc.set_time(hh, mm, ss)
    show_temp_message("F1: Set Time", formatted_full, hold_sec=2)
    res = f"Time Set {formatted_full}"

  elif func == "2" and len(parts) > 1:
    config["motor_speed"] = int(parts[1])
    save_config()
    show_temp_message("F2: Set Speed", f"{config['motor_speed']}%", hold_sec=2)
    res = f"Speed Target Set {config['motor_speed']}%"

  elif func == "3":
    lux = bh.read_lux()
    show_temp_message("F3: Read Lux", f"Lux: {lux}", hold_sec=2)
    res = f"Current Lux: {lux}"

  elif func == "4":
    config["timer_active"] = False
    save_config()
    show_temp_message("F4: TIMER OFF", "State: Disabled", hold_sec=2)
    res = "TIMER OFF"

  elif func == "5":
    config["timer_active"] = True
    save_config()
    show_temp_message("F5: TIMER ON", "State: Enabled", hold_sec=2)
    res = "TIMER ON"

  elif func == "6" and len(parts) >= 3:
    try:
      clean_p1 = parts[1].replace(",", "").strip()
      clean_p2 = parts[2].replace(",", "").strip()
      v1 = float(clean_p1)
      v2 = float(clean_p2)
      config["lux_min"] = min(v1, v2)
      config["lux_max"] = max(v1, v2)
      save_config()
      show_temp_message(
          "F6: Lux Range",
          f"{int(config['lux_min'])}-{int(config['lux_max'])} Lux",
          hold_sec=2,
      )
      res = f"Lux Range {int(config['lux_min'])}-{int(config['lux_max'])}"
    except Exception as e:
      res = f"Lux Set Err: {e}"

  elif func == "7":
    show_temp_message(
        "F7: Lux Target",
        f"{int(config['lux_min'])}-{int(config['lux_max'])} Lux",
        hold_sec=2,
    )
    res = f"Lux Target: {int(config['lux_min'])}-{int(config['lux_max'])}"

  elif func == "8" and len(parts) > 1:
    _, _, _, formatted_full = parse_time_str(",".join(parts[1:]))
    config["t1_start"] = formatted_full
    save_config()
    show_temp_message("F8: Start T1", config["t1_start"], hold_sec=2)
    res = f"T1 Start: {config['t1_start']}"

  elif func == "9" and len(parts) > 1:
    _, _, _, formatted_full = parse_time_str(",".join(parts[1:]))
    config["t1_stop"] = formatted_full
    save_config()
    show_temp_message("F9: Stop T1", config["t1_stop"], hold_sec=2)
    res = f"T1 Stop: {config['t1_stop']}"

  elif func == "10":
    show_temp_message(
        f"Start {config['t1_start']}",
        f"Stop  {config['t1_stop']}",
        hold_sec=2,
    )
    res = f"T1 Range: {config['t1_start']}-{config['t1_stop']}"

  elif func == "11" and len(parts) > 1:
    _, _, _, formatted_full = parse_time_str(",".join(parts[1:]))
    config["t2_start"] = formatted_full
    save_config()
    show_temp_message("F11: Start T2", config["t2_start"], hold_sec=2)
    res = f"T2 Start: {config['t2_start']}"

  elif func == "12" and len(parts) > 1:
    _, _, _, formatted_full = parse_time_str(",".join(parts[1:]))
    config["t2_stop"] = formatted_full
    save_config()
    show_temp_message("F12: Stop T2", config["t2_stop"], hold_sec=2)
    res = f"T2 Stop: {config['t2_stop']}"

  elif func == "13":
    show_temp_message(
        f"Start {config['t2_start']}",
        f"Stop  {config['t2_stop']}",
        hold_sec=2,
    )
    res = f"T2 Range: {config['t2_start']}-{config['t2_stop']}"

  else:
    show_temp_message("Invalid Cmd", clean_cmd, hold_sec=2)
    res = f"Unknown Cmd: {clean_cmd}"

  print(f"[Terminal Result] -> {res}")
  return res


key_buffer = ""
is_typing = False
last_pressed = None


def scan_keypad():
  global key_buffer, is_typing, last_pressed
  current_pressed = None

  for c_idx, col_pin in enumerate(cols):
    col_pin.value(0)
    time.sleep_us(20)
    for r_idx, row_pin in enumerate(rows):
      if row_pin.value() == 0:
        current_pressed = KEY_MAP[r_idx][c_idx]
        break
    col_pin.value(1)
    if current_pressed is not None:
      break

  if current_pressed is not None and current_pressed != last_pressed:
    time.sleep_ms(30)
    last_pressed = current_pressed

    # 1. กด '*' เพื่อเปิดโหมดป้อนคำสั่ง
    if current_pressed == "*":
      is_typing = True
      key_buffer = ""
      lcd.move_to(0, 1)
      lcd.putstr("Cmd:*           ")

    # 2. เมื่ออยู่ในโหมดป้อนคำสั่ง
    elif is_typing:
      if current_pressed == "#":
        cmd = key_buffer
        key_buffer = ""
        is_typing = False
        return cmd
      elif current_pressed == "A":
        key_buffer += ","
      elif current_pressed == "B":
        key_buffer += ":"
      else:
        if len(key_buffer) < 12:
          key_buffer += str(current_pressed)

      lcd.move_to(0, 1)
      lcd.putstr(f"Cmd:*{key_buffer:<11}")

    # 3. กรณีไม่ได้กด '*' นำหน้า (กดเลขเพียวๆ เช่น 3, 4, 5 แล้วกด #)
    else:
      if current_pressed == "#":
        cmd = key_buffer
        key_buffer = ""
        return cmd
      elif current_pressed == "A":
        key_buffer += ","
      elif current_pressed == "B":
        key_buffer += ":"
      else:
        if len(key_buffer) < 12:
          key_buffer += str(current_pressed)

      lcd.move_to(0, 1)
      lcd.putstr(f"Cmd:{key_buffer:<12}")

  elif current_pressed is None:
    last_pressed = None

  return None


# =========================================================
# MAIN LOOP CONTROL
# =========================================================
load_config()

# Listener อ่านค่าจาก Thonny Terminal (sys.stdin) แบบ Non-blocking
poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)

show_temp_message("Receiver Ready", "System Started", hold_sec=2)
print_terminal_menu()

last_tick = 0
last_lux_read_tick = 0
current_lux = 0.0
rx_buf = ""

while True:
  # 1. อ่านคำสั่งจาก Thonny Terminal Shell
  poll_results = poll_obj.poll(0)
  if poll_results:
    line = sys.stdin.readline()
    if line:
      cmd = clean_string(line)
      if cmd:
        print(f"\n[Terminal Command Received]: '{cmd}'")
        execute_command(cmd)

  # 2. สแกน Keypad
  kp_cmd = scan_keypad()
  if kp_cmd:
    print(f"\n[Keypad Command Received]: '{kp_cmd}'")
    execute_command(kp_cmd)

  # 3. อ่านข้อมูล UART จากตัวส่ง (Sender / Web App / Firebase)
  if uart2.any():
    try:
      data = uart2.read().decode("utf-8", "ignore")
      rx_buf += data
      if "#" in rx_buf:
        cmds = rx_buf.split("#")
        rx_buf = cmds[-1]
        for c in cmds[:-1]:
          c_clean = clean_string(c)
          if c_clean:
            print(f"\n[UART/Web Command Received]: '{c_clean}'")
            reply = execute_command(c_clean)
            uart2.write((reply + "\n").encode("utf-8"))
    except:
      rx_buf = ""

  # 4. ลูปประมวลผลเซนเซอร์ + มอเตอร์ + วาดหน้าจอ LCD
  if time.ticks_ms() - last_tick > 100:
    last_tick = time.ticks_ms()

    # อ่านเวลาจาก DS3231
    hh, mm, ss = rtc.get_time_tuple()
    curr_sec = (hh * 3600) + (mm * 60) + ss
    current_time_full = "{:02d}:{:02d}:{:02d}".format(hh, mm, ss)

    # อ่านค่า Lux ทุกๆ 500ms
    if time.ticks_diff(time.ticks_ms(), last_lux_read_tick) > 500:
      last_lux_read_tick = time.ticks_ms()
      current_lux = float(bh.read_lux())

    # เช็กช่วงเวลา T1 และ T2
    in_t1 = is_time_in_range(
        config.get("t1_start", "00:00:00"),
        config.get("t1_stop", "00:00:00"),
        curr_sec,
    )
    in_t2 = is_time_in_range(
        config.get("t2_start", "00:00:00"),
        config.get("t2_stop", "00:00:00"),
        curr_sec,
    )
    in_time = in_t1 or in_t2

    try:
      min_l = float(config.get("lux_min", 10.0))
      max_l = float(config.get("lux_max", 1000.0))
    except:
      min_l, max_l = 10.0, 1000.0

    real_min = min(min_l, max_l)
    real_max = max(min_l, max_l)

    # ลอจิกควบคุมมอเตอร์
    if not config.get("timer_active", True):
      target_spd = config.get("motor_speed", 80)
    else:
      if in_time and (real_min <= current_lux <= real_max):
        target_spd = config.get("motor_speed", 80)
      else:
        target_spd = 0

    apply_motor_hardware_pwm(target_spd)

    # วาดหน้าจอหลัก LCD
    if (
        time.ticks_diff(time.ticks_ms(), lcd_hold_until) > 0
        and not is_typing
        and not key_buffer
    ):
      lux_val_str = str(int(current_lux))
      lux_display = f"L:{lux_val_str}"

      line1_formatted = "{:<8}{:>7} ".format(
          current_time_full, lux_display
      )[:16]
      lcd.move_to(0, 0)
      lcd.putstr(line1_formatted)

      lcd.move_to(0, 1)
      tm_status = "ON " if config.get("timer_active", True) else "OFF"
      lcd.putstr(
          "Spd:{:<3}%  TM:{}  ".format(current_motor_pwm, tm_status)[:16]
      )

  time.sleep_ms(10)