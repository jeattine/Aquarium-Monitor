#
# Script to generate calibration values for the Aquarium Monitor
#
# Follow the prompts to enter 3 or more coordinates where: 
#    x = (PH of the calibration solution)
#    y = (digital value read from the gpio device)
#
# Because our aquarium is expected to be between 8.0 - 8.5, the calibration
# solutions used should span a range before and after these values.
#
import sys
import numpy as np

def calculate_slope_and_offset(coords):
    """
    Calculates slope (m) and y-offset (b) for y = mx + b.
    """
    if len(coords) < 2:
        return None, None

    x, y = zip(*coords)
    try:
        # Returns [slope, intercept]
        m, b = np.polyfit(x, y, 1)
        return m, b
    except Exception as e:
        print(f"Calculation error: {e}")
        return None, None

def main():
    print("--- Aquarium pH Calibration Tool ---")
    print("Enter coordinates as 'pH, ADC_Value' (e.g., 7.0, 812)")
    print("Press Enter on an empty line to finish.\n")

    coordinates = []
    
    while True:
        raw_input = input(f"Point #{len(coordinates) + 1}: ").strip()
        
        if not raw_input:
            if len(coordinates) < 2:
                print("Error: You need at least 2 points (3 recommended).")
                continue
            break
            
        try:
            # Handle potential typos or missing commas
            parts = raw_input.split(',')
            if len(parts) != 2:
                raise ValueError("Include exactly one comma between values.")
                
            x = float(parts[0].strip())
            y = float(parts[1].strip())
            coordinates.append((x, y))
        except ValueError as e:
            print(f" Invalid input: {e}. Please try again.")

    m, b = calculate_slope_and_offset(coordinates)

    if m is not None:
        print("\n" + "="*30)
        print(f"Points analyzed: {len(coordinates)}")
        print(f"Line Equation: y = {m:.4f}x + {b:.4f}")
        
        inv_m = 1/m
        print(f"Calibration: Slope={m:.4f}, Offset={b:.4f}")
        # The calibration file want the 'inverse' slope
        print(f"\nConfig file PH parameters to use: {inv_m:.4f}, {b:.4f}")
        print("="*30)

if __name__ == '__main__':
    main()
