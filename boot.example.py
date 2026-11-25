import network
import time

# Copy this file to boot.py on the MicroPython device, then fill in your Wi-Fi details.
# boot.py is intentionally excluded from Git so credentials are not uploaded.
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASS = "YOUR_WIFI_PASSWORD"


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(False)
    time.sleep_ms(500)
    wlan.active(True)

    if not wlan.isconnected():
        print("Connecting to WiFi:", WIFI_SSID)
        wlan.connect(WIFI_SSID, WIFI_PASS)

        retry = 0
        while not wlan.isconnected() and retry < 20:
            time.sleep(1)
            retry += 1
            print(".", end="")
        print()

    if wlan.isconnected():
        print("WiFi Connected Successfully!")
        print("IP Address:", wlan.ifconfig()[0])
    else:
        print("WiFi Connection Failed! Please check SSID and Password.")


connect_wifi()
