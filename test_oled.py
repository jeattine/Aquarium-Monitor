# Test the OLED Display

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from gpiozero import MCP3008
import time

# Setup the OLED
# The port=1 usually corresponds to the pins 3 & 5 we used
serial = i2c(port=1, address=0x3C)
device = ssd1306(serial)

# Setup a sample sensor (using your new speed setting)
test_sensor = MCP3008(channel=4, clock_pin=11, mosi_pin=10, miso_pin=9, select_pin=8)

try:
    print("OLED active... Press Ctrl+C to stop.")
    while True:
        # Get raw value (0-1023)
        raw_value = test_sensor.value
        val = int(raw_value * 1023)
        
        with canvas(device) as draw:
            # --- YELLOW ZONE (Top 16 Pixels) ---
            # Keep y between 0 and 5
            draw.text((5, 0), "AQUAMON REEF SYSTEM", fill="white") 
    
            # --- THE "GAP" (Avoid y=14 to y=18) ---

            # --- BLUE ZONE (Remaining Pixels) ---
            # Start y at 22 or lower
            draw.text((5, 22), f"Temp: 78.5 F", fill="white")
            draw.text((5, 37), f"pH: 8.2", fill="white")
            draw.text((5, 52), f"CH4 Raw: {val}", fill="white")            
            time.sleep(1)
        
except KeyboardInterrupt:
    print("Cleaning up...")