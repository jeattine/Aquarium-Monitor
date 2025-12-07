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
    Calculates the slope (m) and y-offset (b) of the line of best fit 
    for three or more 2D coordinates using linear regression.

    Args:
        coords (list of tuples/lists): A list of (x, y) coordinates.
                                        e.g., [(x1, y1), (x2, y2), (x3, y3)]

    Returns:
        tuple: A tuple (slope, offset).
    """
    # 1. Separate the x and y coordinates
    # The zip function transposes the list of coordinates.
    x_coords, y_coords = zip(*coords)

    # Convert to NumPy arrays for calculation
    x = np.array(x_coords)
    y = np.array(y_coords)

    # 2. Perform Linear Regression
    # np.polyfit(x, y, 1) calculates the coefficients for a first-degree polynomial (a line).
    # It returns [m, b] where m is the slope and b is the y-offset.
    try:
        # coefficients will be [slope, y_offset]
        coefficients = np.polyfit(x, y, 1) 
        slope = coefficients[0]
        offset = coefficients[1]
        
        return slope, offset
    
    except np.linalg.LinAlgError as e:
        # This error is highly unlikely with 3 or more points unless all x-values are the same (vertical line).
        print(f"Error during calculation: {e}")
        return None, None

def main(): 
    coordinates = list()
    counter = 1
    while True:
        try:
            while True:
                coordinate = input("Enter coordinate #{} in form: x,y: ".format(counter))
                if len(coordinate) == 0:
                    break
                print('Coordinate {}: {}'.format(counter, coordinate))
                while True:
                    proceed = input("Type (R) to re-enter coordinate or press Enter to proceed to next coordinate: ")
                    if proceed == "" or proceed == 'R' or proceed == 'r':
                        break
                if proceed == "":
                    break
            x_y_str = coordinate.split(',')      
            x_y = [float(x_y_str[0]), float(x_y_str[1])]
            coordinates.append(x_y)
            counter += 1
        except  ValueError:
            break
    # Calculate the slope and offset
    m, b = calculate_slope_and_offset(coordinates)

    if m is not None:
        print(f"Results for Coordinates {coordinates}")
        print(f"Slope (m): {m:.4f}")
        print(f"Y-Offset (b): {b:.4f}")
        print(f"Equation of the line of best fit: y = {m:.4f}x + {b:.4f}")
        print("\nConfig file PH parameters to use: {0:.4f}, {1:.4f}".format(1/m, b))
    
if __name__ == '__main__':
    main()
