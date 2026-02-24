# test digital inputs

from gpiozero import Button
from time import sleep

# Define your list of pins
input_pins = [4, 5, 16, 17, 18, 19, 20, 21, 22, 23, 24]

# Create a list of Button objects
# pull_up=True is the default; it assumes your switch connects the pin to Ground
inputs = [Button(pin) for pin in input_pins]

print("--- Digital Input Test ---")
print("Press Ctrl+C to stop")

try:
    while True:
        results = []
        for i, btn in enumerate(inputs):
            # is_pressed returns True if the pin is connected to GND
            status = "ACTIVE" if btn.is_pressed else "inactive"
            results.append(f"GPIO{input_pins[i]}: {status}")
        
        # Print everything on one line that refreshes
        print(f"\x1b[2K\r{' | '.join(results)}", end="", flush=True)
        sleep(0.5)
except KeyboardInterrupt:
    print("\nTest stopped.")