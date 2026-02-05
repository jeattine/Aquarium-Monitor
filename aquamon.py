#!/usr/bin/env python3

# Script to monitor reef aquarium

import sys
import os
import shutil
import time
import math
import smtplib
import statistics
import logging
import socket
import subprocess
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import timedelta, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from collections import deque
from gpiozero import MCP3008, DigitalInputDevice, Button
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas

# --- HARDWARE MAPPING ---
# MCP3008 Chip 0: Channels 0-7 (Temp, PH, etc.)
# MCP3008 Chip 1: Channels 8+
# OLED: I2C Address 0x3C
# Buttons: GPIO 23 (pH Low Calibrate), GPIO 24 (pH High Calibrate)

class Gpio:
    def __init__(self, gpio_controller, config_file_data):
        self.controller = gpio_controller
        self.config_info = config_file_data
        # Initialize very old time
        self.last_sent_alert = datetime.now() - timedelta(days=365)
        self.nag_level = int(self.config_info[2].lstrip())
        self.test_active = False

    def read_value(self):
        # Needs to be implemented in the derived classes
        raise NotImplementedError

    def test(self):
        current_value = self.read_value()
        if not self.test_active:
            if current_value < 0 or self.controller.start_time + timedelta(seconds=90) > datetime.now():
                return current_value
        self.test_active = True
        if self.controller.calibrate:
            return current_value
        conditions = self.config_info[4].lstrip().split('+')
        for condition in conditions:
            if ':' in condition:
                time_value = condition.split('?')
                timespan = time_value[0].split('-')
                time_start = timespan[0]
                time_end = timespan[1]
                value = time_value[1].split('-')
            else:
                time_start = ''
                time_end = ''
                value = condition.split('-')
            value_low = value[0]
            if len(value) == 2:
                value_high = value[1]
            else:
                value_high = value[0]

            # Are we in the indicated time range?
            if not time_start or self.in_time_range(time_start, time_end):
                if current_value < float(value_low) or current_value > float(value_high):
                    # Read the nag level and timestamp of last email,
                    # If beyond the no-nag window, send the alert email.
                    if (self.last_sent_alert + timedelta(hours=self.nag_level)) < datetime.now():
                        self.controller.email_text.append(f'{self.read_label()} Alert!\n')
                        self.last_sent_alert = datetime.now()
                        # force a server update prior to sending the alarm
                        self.controller.report_calls = self.controller.server_update_freq / self.controller.sample_time

        return current_value

    def in_time_range(self, time_start, time_end):
        now = datetime.now().time()
        start = datetime.strptime(time_start, "%H:%M").time()
        end = datetime.strptime(time_end, "%H:%M").time()
    
        if start <= end:
            return start <= now <= end
        else: # Overnights (e.g., 22:00 to 02:00)
            return now >= start or now <= end
		
    def read_label(self):
        return self.config_info[3].lstrip()
        
    def log(self, value):
        # Let the derived classes optionally maintain a log.
        pass

class GpioAnalog(Gpio):
    def __init__(self, gpio_controller, config_file_data, enable_averaging = True):
        super(GpioAnalog, self).__init__(gpio_controller, config_file_data)
        self.averaged_sample = -1.0
        self.enable_averaging = enable_averaging
        # create a 16 entry buffer with values spanning the 10 bit A/D converter range
        # Initialize a deque with a fixed maximum length.
        # This replaces manual slicing [1:]
        self.samples = deque(range(0, 1024, 64), maxlen=16)

    def read_value(self):
        return self.averaged_sample

    def read_condition(self):
        return f'range:{self.config_info[4].strip()}'

    def read_value_text(self, value):
        return f'{value:6.1f}'

    def read_sensor_and_update(self):
         # Simply append; the oldest value is dropped automatically  
        new_val = self.controller.read_analog(self.config_info[1].lstrip())
        self.samples.append(new_val)
        # Create a running averaged sample dumping the 1/8th highest and 1/8th lowest samples
        if self.enable_averaging:
            temp_samples = sorted(list(self.samples))
            # Trim 25% lowest and 25% highest
            trim_low = int(len(temp_samples)/8)
            trim_high = int(len(temp_samples)) - trim_low
            temp_samples = temp_samples[trim_low:trim_high]

            self.averaged_sample = sum(temp_samples) / len(temp_samples)

class GpioDigital(Gpio):
    def __init__(self, gpio_controller, config_file_data):
        super(GpioDigital, self).__init__(gpio_controller, config_file_data)
        self.snapshot = -1
        self.ones_count = 0
        self.zeros_count = 0
        self.ones_total = 0
        self.zeros_total = 0
        self.previous_state = 0

    def read_value(self):
        return self.snapshot

    def read_condition(self):
        return ' '

    def read_value_text(self, value):
        if value == 0:
            return self.config_info[5].strip()
        elif value == 1:
            return self.config_info[6].strip()
        return 'Not Avail'

    def read_sensor_and_update(self):
        count = self.controller.read_digital(self.config_info[1].lstrip())
        if count == 1:
            if self.previous_state == 0:
                self.previous_state = 1
                self.zeros_count = 0
            self.ones_count += 1
            self.ones_total += 1
        else:
            if self.previous_state == 1:
                self.previous_state = 0
                self.ones_count = 0
            self.zeros_count += 1
            self.zeros_total += 1
        if self.ones_count > 3:
            self.snapshot = 1
        elif self.zeros_count > 3:
            self.snapshot = 0

class FloorWetSensor(GpioDigital):
    def __init__(self, gpio_controller, config_file_data):
        super(FloorWetSensor, self).__init__(gpio_controller, config_file_data)

class CO2deliverySensor(GpioDigital):
    def __init__(self, gpio_controller, config_file_data):
        super(CO2deliverySensor, self).__init__(gpio_controller, config_file_data)

    def read_value_text(self, value):
        # Do not require >3 samples of the same reading, i.e. ignore 'value'
        if self.zeros_count > 0:
            minutes_on = (self.zeros_count * self.controller.sample_time)/60
            retval = self.config_info[5].strip() + f' {minutes_on:.0f} minutes.'
        elif self.ones_count > 0:
            minutes_off = (self.ones_count * self.controller.sample_time)/60
            retval = self.config_info[6].strip() + f' {minutes_off:.0f} minutes.'
        else:
            return 'Not Avail'
        percent_on = (self.zeros_total * 100) / (self.zeros_total + self.ones_total)
        return retval + f' (overall on-time: {percent_on:.0f}%)'

class TempSensor(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(TempSensor, self).__init__(gpio_controller, config_file_data)
        self.ema_value = None
        self.alpha = 0.2  # 20% of new average mixed with 80% previous

    def read_sensor_and_update(self):
        # Use parent logic to get the trimmed mean
        super().read_sensor_and_update()
        current_trimmed_mean = self.averaged_sample

        # Apply Exponential Moving Average (EMA)
        if self.ema_value is None:
            self.ema_value = current_trimmed_mean
        else:
            self.ema_value = (self.alpha * current_trimmed_mean) + ((1 - self.alpha) * self.ema_value)
        
        # Overwrite the result used for Temperature calculation
        self.averaged_sample = self.ema_value

    def read_value(self):
        pad_resistor = float(self.config_info[5].lstrip())
        #[Ground] -- [10k-pad-resistor] -- | -- [thermistor] --[Vcc (5v)]
        if self.averaged_sample == 0:
            return 0
        if self.averaged_sample < 0:
            return 0
        resistance = ((1024 * pad_resistor / self.averaged_sample) - pad_resistor)

        #**************************************************************
        # Utilizes the Steinhart-Hart Thermistor Equation:
        #    Temperature in Kelvin = 1 / {A + B[ln(R)] + C[ln(R)]^3}
        #    where A = 0.001129148, B = 0.000234125 and C = 8.76741E-08
        #**************************************************************
        ln_r = math.log(resistance)
        A, B, C = 1.129148e-3, 2.34125e-4, 8.76741e-8
        temp = 1 / (A + B * ln_r + C * math.pow(ln_r, 3))
        #Convert from Kelvin the Celsius
        temp = temp - 273.15
        # Convert to Fahrenheit.
        temp = (temp * 9.0) / 5.0 + 32.0
        # Adjust with calibration value
        calibration = float(self.config_info[6].lstrip())
        
        # Store water temp in controller for display
        if "Water" in config_info[3].strip():
            controller.current_temp = temp + calibration

        return temp + calibration

class RandomFlowSensor(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(RandomFlowSensor, self).__init__(gpio_controller, config_file_data, False)
        # set the sample buffer to 128 entries
        self.samples = deque(range(0,1024,8), maxlen=128)

    def read_value(self):
        # Convert the sample data into a standard deviation
        return statistics.stdev(self.samples)

class FlowSensorFX4(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(FlowSensorFX4, self).__init__(gpio_controller, config_file_data)
       
    def read_value(self):
        flow_volume = 1023 - self.averaged_sample
        return flow_volume

class LightSensor(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(LightSensor, self).__init__(gpio_controller, config_file_data)

    def read_value(self):
        light_level = 1023 - self.averaged_sample
        return light_level

class HighLowLevel(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(HighLowLevel, self).__init__(gpio_controller, config_file_data)

    def read_value(self):
        level = self.averaged_sample
        return level
    def read_value_text(self, value):
        if value > 768.0:
            return self.config_info[5].strip()
        elif value < 256.0:
            return self.config_info[6].strip()
        return self.config_info[7].strip()

class Battery(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(Battery, self).__init__(gpio_controller, config_file_data)
        # initialize buffer with a value close to what is expected
        self.samples = deque([910] * 16, maxlen=16)

    def read_value(self):
        # ---------------------------------------------------------------------------
        # Requires the following configuration: 
        #(+12V battery)--(10K ohm)--(+GPIO input)--(2.8K ohm)--(-battery)--(-GPIO input)
        # Translates the 0V-14.97V --> 0V-3.3V --> digital 0-1023
        #----------------------------------------------------------------------------
        if self.controller.calibrate:
            print(f'Battery raw digital: {self.averaged_sample}')
            return self.averaged_sample
        voltage = self.averaged_sample/68.31
        return voltage
        
    def read_value_text(self, value):
        if value > float(self.config_info[5].strip()):
            return f' {self.config_info[6].strip()} ({value:2.1f})'
        elif value > float(self.config_info[7].strip()):
            return f' {self.config_info[8].strip()} ({value:2.1f})'
        return f' {self.config_info[9].strip()} ({value:2.1f})'
            
class Ph(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(Ph, self).__init__(gpio_controller, config_file_data)
        # This class tracks the max and min values/timestamps and logs PH values every hour
        self.slope = float(self.config_info[5].lstrip())
        self.offset = float(self.config_info[6].lstrip())
        self.samples = deque([(8.1 * self.slope + self.offset) * 16, maxlen=16)       
        self.ema_value = None
        self.alpha = 0.2  # 20% of new average mixed with 80% previous
        self.raw_low = None
        self.raw_high = None

        self.min_max_init()
        self.log_stamp = datetime.now().hour   
        log_path = self.controller.base_path / 'phlog.txt'
        self.ph_logger = logging.getLogger("PhLogger")
        self.ph_logger.setLevel(logging.INFO)
        
        # Avoid adding multiple log handlers if the class is re-instantiated
        if not self.ph_logger.handlers:
            # Keep 5 backup files, each max 1MB
            handler = RotatingFileHandler(log_path, maxBytes=10**6, backupCount=5)
            # Standard CSV-like format: Time,Value
            formatter = logging.Formatter('%(asctime)s,%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            handler.setFormatter(formatter)
            self.ph_logger.addHandler(handler)    
        
    def read_sensor_and_update(self):
        # Use parent class logic to get the trimmed mean
        super().read_sensor_and_update()
        current_trimmed_mean = self.averaged_sample

        # Apply Exponential Moving Average (EMA)
        if self.ema_value is None:
            self.ema_value = current_trimmed_mean
        else:
            self.ema_value = (self.alpha * current_trimmed_mean) + ((1 - self.alpha) * self.ema_value)      
        # Overwrite the result used for PH calculation
        self.averaged_sample = self.ema_value

    def read_value(self):
        current_day = datetime.now().day
        if current_day != self.day_stamp:
            # Start a new max/min period of recording
            self.min_max_init()
        
        ph = (self.averaged_sample - self.offset) / self.slope
        
        # Record PH in controller for Desplay Panel
        controller.current_ph = ph
        
        if self.test_active:         
            if ph > self.max_ph:
                self.max_ph = ph
                self.max_timestamp = datetime.now()
            if ph < self.min_ph:
                self.min_ph = ph
                self.min_timestamp = datetime.now()
        return ph

    def min_max_init(self):
        self.max_ph = 4
        self.min_ph = 12
        self.max_timestamp = datetime.now()
        self.min_timestamp = datetime.now()
        self.day_stamp = datetime.now().day    
        
    def log(self, value):
        current_hour = datetime.now().hour
        if current_hour != self.log_stamp:
            # Logging library handles the timestamp and file writing
            self.ph_logger.info(f"{value:2.1f}")
            self.log_stamp = current_hour
            
    def read_value_text(self, value):
        # need to include the mix/max values/timestamps
        min_ts = self.min_timestamp.strftime("%I:%M %p")
        max_ts = self.max_timestamp.strftime("%I:%M %p")
        return f'{value:2.1f}  max:{self.max_ph:3.1f} at {max_ts}  min:{self.min_ph:3.1f} at {min_ts}'

    def calibrate(self, target):
        # Capture the current raw value from the running average
        raw = self.averaged_sample
        if target == self.controller.ph_calibrate_low:
            self.raw_low = raw
        else:
            self.raw_high = raw
        
        if self.raw_low and self.raw_high:
            self.slope = (self.raw_high - self.raw_low) /  (self.controller.ph_calibrate_high - self.controller.ph_calibrate_low)
            self.offset = self.controller.ph_calibrate_low - (self.raw_low / self.slope)
            self.save_to_config()
            # Reset the stored calibration data to allow re-calibration
            self.raw_low = 0
            self.raw_high = 0

    def save_to_config(self):
        filename = 'config.txt'
        updated_lines = []
        
        try:
            with open(filename, 'r') as f:
                lines = f.readlines()
            
            for line in lines:
                # Identify the pH line (starts with 'ph')
                if line.strip().startswith('ph,'):
                    parts = line.split(',')
                    # parts[0]=class, [1]=gpio, [2]=nag, [3]=label, [4]=condition
                    # parts[5]=slope, [6]=offset
                    
                    # We preserve the first 5 fields exactly as they are
                    parts[5] = f" {self.slope:.4f}"
                    # Append newline to the last part
                    parts[6] = f" {self.offset:.4f}\n"
                    
                    new_line = ",".join(parts)
                    updated_lines.append(new_line)
                    print(f"Updated config line: {new_line.strip()}")
                else:
                    updated_lines.append(line)
            
            # Write the updated content back to the file
            with open(filename, 'w') as f:
                f.writelines(updated_lines)
            
            print("Successfully saved new calibration to config.txt")
            
        except Exception as e:
            print(f"Error saving calibration: {e}")       

class CalibrationButtons:
    def __init__(self, ph_sensor, controller):
        self.ph = ph_sensor
        self.controller = controller
        self.btn_low = Button(23, bounce_time=0.1)
        self.btn_high = Button(24, bounce_time=0.1)
        
        self.btn_low.when_pressed = lambda: self.ph.calibrate(controller.ph_calibrate_low)
        self.btn_high.when_pressed = lambda: self.ph.calibrate(controller.ph_calibrate_high)

class GpioCtl:
    def __init__(self):
        self.my_gpios = []
        self.email_text = [] 
        self.connected = False
        self.settings_found = []
        self.settings_unexpected = []
        self.settings_missing = []
        self.start_time = datetime.now()
        self.start_time_str = self.start_time.strftime("%A %B %d %I:%M:%S %p")
        self.display_ph = 0.0
        self.display_temp = 0.0
        
        # List of required environment variables
        required_vars = {
            'gpio_pw': 'AQUAMON_GPIO_PW',
            'me': 'AQUAMON_EMAIL',
            'email_pw': 'AQUAMON_EMAIL_PW',
            'recipients': 'AQUAMON_RECIPIENTS'
        }
        # Mapping config keys to Class names
        self.SENSOR_MAP = {
            'gpioa': GpioAnalog,
            'gpiod': GpioDigital,
            'temp': TempSensor,
            'rflow': RandomFlowSensor,
            'flow': FlowSensorFX4,
            'light': LightSensor,
            'floor': FloorWetSensor,
            'co2': CO2deliverySensor,
            'hilow': HighLowLevel,
            'battery': Battery,
            'ph': Ph
        }
        # Global integer settings
        self.global_integers = [
            'connect_timeout',
            'reconnect_delay',
            'reconnect_attempts',
            'server_update_freq',
            'sample_time'
        ]    
        
        # Global float settings
        self.global_floats = [
            'ph_calibrate_low',
            'ph_calibrate_high'            
        ]
        
        # All required global settings
        self.global_settings = self.global_integers + self.global_floats + [
            'smtp',
            'email_subject',
            'cloud_store',
            'local_filepath'
        ]           

        # Digital Pin Mapping (Hex from config -> Pi GPIO)
        self.digital_map = {
            # config GPIO Number,  Raspberry PI BCM Number
            '17': DigitalInputDevice(4, pull_up=True),  # pin 7
            '18': DigitalInputDevice(17, pull_up=True), # pin 11
            '19': DigitalInputDevice(27, pull_up=True), # pin 13
            '20': DigitalInputDevice(22, pull_up=True), # pin 15
            '21': DigitalInputDevice(5, pull_up=True),  # pin 29
            '22': DigitalInputDevice(6, pull_up=True),  # pin 31
            '23': DigitalInputDevice(26, pull_up=True), # pin 37
            '24': DigitalInputDevice(25, pull_up=True)  # pin 22
            # BCM's 23 and 24 are used for the calibration buttons
        }
        
        # Analog mapping is a sequential map of GPIO number to channel
        #    GPIO 1-8 ->  maps to chip 1, channels 0-7
        #    GPIO 9-16 -> maps to chip 2, channels 0-7

        # Make sure required env vars are set and exit immediately if not.
        for attr, env_var in required_vars.items():
            value = os.environ.get(env_var)
            if value is None:
                sys.exit(f"Critical Error: {env_var} is not set.")
            setattr(self, attr, value)        

        print(f"Alerts will be sent to the following recipients: {self.recipients}")
        
        # Are we requested to run in calibration mode?
        self.calibrate = len(sys.argv) > 1 and sys.argv[1] == 'Calibrate'
        self.load_config('config.txt')

        # Initialize ADCs
        self.chip1 = [MCP3008(channel=i, device=0) for i in range(8)]
        self.chip2 = [MCP3008(channel=i, device=1) for i in range(8)]
        
        # Initialize OLED
        try:
            serial = i2c(port=1, address=0x3C)
            self.display = ssd1306(serial)
        except:
            self.display = None
            print("OLED not found, continuing without display.")
        
        # Initialize reported calls to force a server update at startup
        self.report_calls = self.server_update_freq / self.sample_time
        
    def load_config(self, filename):
        with open(filename, 'r') as gpio_config:
            for line in gpio_config:
                # Handle global configuration settings
                line = line.strip()
                if not line or line[0] == '#' or '=' in line:
                    # Handle global settings (username, password, etc.)
                    if '=' in line:
                        self.parse_setting(line)
            # Define the base directory using pathlib
            self.base_path = Path(self.local_filepath) / self.cloud_store
        
            # Ensure the directory exists (create it if it doesn't)
            self.base_path.mkdir(parents=True, exist_ok=True)  

            # Move through the file again, this time collecting sensor configuration
            gpio_config.seek(0)
            
            for line in gpio_config: 
                # Handle sensor instantiations
                parts = line.split(',')
                prefix = parts[0].lower()
                
                # Check if the prefix matches one of our known sensor types
                for key, sensor_class in self.SENSOR_MAP.items():
                    if prefix.startswith(key):
                        self.my_gpios.append(sensor_class(self, parts))
                        break
            if self.settings_unexpected:
                print(f"Warning, unrecognized setting(s) detected: {self.settings_unexpected}")            
            self.settings_missing = list(set(self.global_settings) - set(self.settings_found))
            if self.settings_missing:
                sys.exit(f'Missing setting(s) in config.txt file: {self.settings_missing}')

    def parse_setting(self, line):
        key, value = line.split('=', 1)
        # Use setattr to dynamically assign properties to the class instance
        if key.strip() in self.global_integers:
            try:
                value_int = int(value.strip())
            except Exception as error:
                sys.exit(f'Specified value for {key.strip()} must be an integer!')
            setattr(self, key.strip(), value_int)
        elif key.strip() in self.global_floats:
             try:
                value_float = float(value.strip())
            except Exception as error:
                sys.exit(f'Specified value for {key.strip()} must be a floating point number!')
            setattr(self, key.strip(), value_float)
        else:
            setattr(self, key.strip(), value.strip())
        if key.strip() in self.global_settings:
            self.settings_found.append(key.strip())
        else:
            self.settings_unexpected.append(key.strip())

    def read_analog(self, gpio_num):
        pin = int(gpio_num) - 1
        # Scale to 1024
        if pin <= 7:
            return int(self.chip1[pin].value * 1024)
        else:
            return int(self.chip2[pin-8].value * 1024)

    def read_digital(self, gpio_num):
        label = str(gpio_num).upper()
        if label in self.digital_map:
            return 1 if self.digital_map[label].is_active else 0
        return 0

    def update_display(self, lines):
        if self.display:
            with canvas(self.display) as draw:
                for idx, line in enumerate(lines):
                    draw.text((0, idx*14), line, fill="white")

    def read_sensors_and_update(self):
        for x in self.my_gpios:
            x.read_sensor_and_update()

    def send_email_alert(self):
        outer = MIMEMultipart()
        outer['Subject'] = self.email_subject
        outer['From'] = self.me
        outer['To'] = self.recipients
        # Add the alert message
        msg = MIMEText("\n".join(self.email_text))
        outer.attach(msg)

        # Path to current status
        status_file = self.base_path / 'current.txt'

        # Attach the current status information
        try:
            contents = status_file.read_text()
            stats = MIMEText(contents.replace(';', '\n'))
            outer.attach(stats)
        except FileNotFoundError:
            print("Warning: current.txt not found for email attachment.")

        # Add a link to check the current status
        email_link = MIMEText(self.cloud_store + 'current.txt\n')
        outer.attach(email_link)
      
        # Send the email
        try:
            with smtplib.SMTP(self.smtp, 587) as server:
                server.ehlo()
                server.starttls()
                server.login(self.me, self.email_pw)
                server.sendmail(self.me, self.recipients.split(','), outer.as_string())
        except Exception as error:
            print(f"Exception={error} Error sending alert!: {msg}")
        # Initialize for next alert
        self.email_text[:] = []

    def test_and_report(self):
        # store the status file to the cloud drive based on the update frequency
        self.report_calls += 1
        
        if (self.report_calls * self.sample_time) > self.server_update_freq or self.email_text:
            self.report_calls = 0
            curDateTimeRaw = datetime.now()
            curDateTime = curDateTimeRaw.strftime("%A %B %d %I:%M:%S %p")
            status_file_path = self.base_path / 'current.txt'
            with status_file_path.open('w') as status_file:
                status_file.write(f'Sample time: {curDateTime}\n')
                status_file.write(f'Monitor start time: {self.start_time_str}\n')
                for gpio in self.my_gpios:
                    current_value = gpio.test()
                    status_file.write(f'{gpio.read_label()}:{gpio.read_value_text(current_value)}\n')
                    try:
                        gpio.log(current_value)
                    except Exception as logerr:
                        print(f"Exception={logerr} Error making log entry for {gpio.read_label()}!")
        if self.email_text:
            alerts = ", ".join(self.email_text)
            clean_alerts = alerts.replace("\n", "")
            print(f"{curDateTime}: {clean_alerts}")
            self.send_email_alert()

def wait_for_internet(host="8.8.8.8", port=53, timeout=3):
    while True:
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return
        except OSError:
            print("Waiting for network...")
            time.sleep(5)
            
def ensure_single_instance(port=65432):
    """Ensures only one instance of the script runs using a local socket."""
    # We create a 'global' variable so the socket isn't garbage collected
    global lock_socket
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # We try to bind to a specific local port
        lock_socket.bind(("127.0.0.1", port))
    except socket.error:
        print("--- ERROR: Aquarium Monitor is already running! ---")
        sys.exit(1)
        
def main():
    print("Starting Aquarium Monitor ...")
    wait_for_internet()
    ensure_single_instance()
    controller = GpioCtl()
    cal_btns = CalibrationButtons(ph)
    while True:
        try:
            controller.read_sensors_and_update()
            controller.test_and_report()
            controller.update_display([
                f"Time: {datetime.datetime.now().strftime('%H:%M')}",
                f"Temp: {controller.current_temp:.1f} F",
                f"PH:   {controller.current_ph:.2f}"
            ])         
            time.sleep(controller.sample_time)
        except KeyboardInterrupt:
            print("User requested termination. Exiting.")
            break
        except Exception as error:
            print(f"Exception={error} Unhandled! Exiting")
            raise

if __name__ == '__main__':
    main()

