import spidev
import smbus2
import time

# --- 1. TEST I2C (OLED) ---
print("Checking I2C Bus for OLED (Address 0x3c)...")
try:
    bus = smbus2.SMBus(1)
    # Try to read a single byte from the OLED address
    bus.read_byte(0x3c)
    print("  [SUCCESS] OLED found at 0x3c")
except Exception:
    print("  [ERROR] OLED NOT FOUND! Check I2C wiring and raspi-config.")

# --- 2. TEST SPI (MCP3008s) ---
spi = spidev.SpiDev()

def read_mcp(chip, channel):
    spi.open(0, chip) # Bus 0, Device (Chip Select) 0 or 1
    spi.max_speed_hz = 500000
    adc = spi.xfer2([1, (8 + channel) << 4, 0])
    data = ((adc[1] & 3) << 8) + adc[2]
    spi.close()
    return data

print("\nChecking MCP3008 Chips (ADC)...")
while True:
    for chip in [0, 1]:
        print(f"--- Chip {chip} ---")
        for chan in range(8):
            val = read_mcp(chip, chan)
            # Identify the state based on your wiring
            state = "Reading"
            if val > 1000: state = "Pulled HIGH (10K)"
            elif val < 20:  state = "Pulled LOW (10K)"
        
            print(f"  Channel {chan}: {val:4d} ({state})")
        time.sleep(2)