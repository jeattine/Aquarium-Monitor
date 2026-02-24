import spidev
import time

spi = spidev.SpiDev()
spi.open(0, 0) # Bus 0, Device 0
spi.max_speed_hz = 500000

# We send [0xAA, 0x55] (10101010 and 01010101)
# This is a perfect pattern to test for interference or shorts.
test_data = [0xAA, 0x55]

try:
    while True:
        # xfer2 sends data and returns what was received simultaneously
        response = spi.xfer2(test_data)
        print(f"Sent: {test_data}  Received: {response}")
        
        if response == test_data:
            print(">>> SUCCESS: Loopback matches!")
        else:
            print(">>> ERROR: Data mismatch.")
            
        time.sleep(1)
except KeyboardInterrupt:
    spi.close()