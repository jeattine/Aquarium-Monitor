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
import spidev
import signal
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo, available_timezones
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from collections import deque
from gpiozero import DigitalInputDevice, Button, LED
from luma.core.interface.serial import i2c
from PIL import ImageFont
from luma.oled.device import ssd1306
from luma.core.render import canvas

# --- HARDWARE I/O MAPPING ---
# MCP3008 Chip 0: Channels 0-7 -> Ports 1-8
# MCP3008 Chip 1: Channels 0-4 -> Ports 9-13 (unused channels 5,6,7)
# OLED: I2C Address 0x3C
# PH-EZO: I2C Address 0x63 (Port 25  BNC connector)
# GPIO 6  (pin 31) used for system restart
# GPIO 12 (pin 32) is used to enable maintenance mode
# GPIO 13 (pin 33) is used for the system LED
# GPIO 24 (pin 18) is used for output to remote LED status
# GPIO 25 (pin 22) used for pH mid Calibrate
# GPIO 27 (pin 13) used for pH High Calibrate

class Sensor:
    def __init__(self, controller, config_file_data):
        self.controller = controller
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
            if current_value < 0 or self.controller.start_time + timedelta(seconds=120) > datetime.now():
                return current_value
        self.test_active = True
        if self.controller.maintenance_mode or self.controller.feed_mode:
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
                    # Set flag that an alarm is active during this round of sampling
                    self.controller.alarm_active = True
                    self.controller.alarm_text = self.config_info[3].strip()
                    # Read the nag level and timestamp of last email,
                    # If beyond the no-nag window, send the alert email.
                    if (self.last_sent_alert + timedelta(hours=self.nag_level)) < datetime.now():
                        self.controller.email_text.append(f'{self.read_label()} Alert!\n')
                        self.last_sent_alert = datetime.now()
                        # force a server update prior to sending the alarm
                        self.controller.report_calls = self.controller.server_update_freq / self.controller.sample_time

        return current_value

    def in_time_range(self, time_start, time_end):
        now = self.controller.convert_to_local_time(datetime.now()).time()
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

class GpioAnalog(Sensor):
    def __init__(self, controller, config_file_data, enable_averaging = True):
        super(GpioAnalog, self).__init__(controller, config_file_data)
        self.averaged_sample = -1.0
        self.enable_averaging = enable_averaging
        self.trim_amount = 8 # Trim 12.5% from top and bottom of sample buffer
        # create a 16 entry buffer with values spanning the 10 bit A/D converter range
        # Initialize a deque with a fixed maximum length.
        # This replaces manual slicing [1:]
        self.samples = deque(range(0, 1024, 64), maxlen=16)
        self.port = int(self.config_info[1].strip())

    def read_value(self):
        return self.averaged_sample

    def read_value_text(self, value):
        return f'{value:6.1f}'

    def read_sensor_and_update(self):
         # Simply append; the oldest value is dropped automatically
        new_val = self.controller.read_analog(self.port)
        self.samples.append(new_val)
        # Create a running average. Dump (1/trim_amount) from highest/lowest samples
        if self.enable_averaging:
            temp_samples = sorted(list(self.samples))
            # Trim 12.5% lowest and 12.5% highest
            trim_low = int(len(temp_samples)/self.trim_amount)
            trim_high = int(len(temp_samples)) - trim_low
            temp_samples = temp_samples[trim_low:trim_high]

            self.averaged_sample = sum(temp_samples) / len(temp_samples)

    def is_port_valid(self):
        return self.port in self.controller.analog_ports

class GpioDigital(Sensor):
    def __init__(self, controller, config_file_data):
        super(GpioDigital, self).__init__(controller, config_file_data)
        self.snapshot = -1
        self.ones_count = 0
        self.zeros_count = 0
        self.ones_total = 0
        self.zeros_total = 0
        self.previous_state = 0
        self.port = self.config_info[1].strip()


    def read_value(self):
        return self.snapshot

    def read_value_text(self, value):
        if value == 0:
            return self.config_info[5].strip()
        elif value == 1:
            return self.config_info[6].strip()
        return 'Not Avail'

    def read_sensor_and_update(self):
        count = self.controller.read_digital(self.port)
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

    def is_port_valid(self):
        return int(self.port) in self.controller.digital_ports

class FloorWetSensor(GpioDigital):
    def __init__(self, controller, config_file_data):
        super(FloorWetSensor, self).__init__(controller, config_file_data)

class TempSensor(GpioAnalog):
    def __init__(self, controller, config_file_data):
        super(TempSensor, self).__init__(controller, config_file_data)
        self.current_temp = 0
        self.ema_value = None
        self.alpha = 0.2  # Smoothing factor
        self.samples = deque([500] * 16, maxlen=16)

        # Check if this instance is the primary water sensor
        self.is_water_sensor = "Water" in self.config_info[3].strip()

    def read_sensor_and_update(self):
        # Get trimmed mean from parent (GpioAnalog)
        super().read_sensor_and_update()
        current_trimmed_mean = self.averaged_sample

        # debugging
        #print(f"{self.samples}\n")

        # Apply Exponential Moving Average (EMA) to smooth jitter
        if self.ema_value is None:
            self.ema_value = current_trimmed_mean
        else:
            self.ema_value = (self.alpha * current_trimmed_mean) + ((1 - self.alpha) * self.ema_value)

        # Calculate Resistance
        pad_resistor = float(self.config_info[5].strip())
        if self.ema_value <= 0:
            self.current_temp = 0
            return

        # Vout = Vin * (R_pad / (R_therm + R_pad)) -> Solving for R_therm:
        resistance = ((1024 * pad_resistor / self.ema_value) - pad_resistor)

        # Steinhart-Hart Equation
        try:
            ln_r = math.log(resistance)
            A, B, C = 1.129148e-3, 2.34125e-4, 8.76741e-8
            temp_k = 1 / (A + B * ln_r + C * math.pow(ln_r, 3))

            # Convert Kelvin to Celsius
            temp_c = temp_k - 273.15
            # Convert to Fahrenheit
            temp_f = (temp_c * 9.0) / 5.0 + 32.0

            # Adjust with calibration offset from config
            calibration = float(self.config_info[6].lstrip())
            self.current_temp = temp_f + calibration

            # Update Controller's display variable
            if self.is_water_sensor:
                self.controller.display_temp = self.current_temp

        except (ValueError, ZeroDivisionError):
            self.current_temp = 0

    def read_value(self):
        return self.current_temp

class RandomFlowSensor(GpioAnalog):
    def __init__(self, controller, config_file_data):
        super(RandomFlowSensor, self).__init__(controller, config_file_data, False)
        # set the sample buffer to 128 entries
        self.samples = deque(range(0,1024,8), maxlen=128)

    def read_value(self):
        # Convert the sample data into a standard deviation
        return statistics.stdev(self.samples)

class LightSensor(GpioAnalog):
    def __init__(self, controller, config_file_data):
        super(LightSensor, self).__init__(controller, config_file_data)

    def read_value(self):
        light_level = 1023 - self.averaged_sample
        return light_level

class HighLowLevel(GpioAnalog):
    def __init__(self, controller, config_file_data):
        super(HighLowLevel, self).__init__(controller, config_file_data)

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
    def __init__(self, controller, config_file_data):
        super(Battery, self).__init__(controller, config_file_data)
        # initialize buffer with a value close to what is expected
        self.samples = deque([910] * 16, maxlen=16)
        self.good_fair_threshold = float(self.config_info[5].strip())
        self.fair_bad_threshold = float(self.config_info[7].strip())
        self.good_text = self.config_info[6].strip()
        self.fair_text = self.config_info[8].strip()
        self.bad_text = self.config_info[9].strip()

    def read_value(self):
        # ---------------------------------------------------------------------------
        # Requires the following configuration:
        #(+12V battery)--(10K ohm)--(+GPIO input)--(2.8K ohm)--(-battery)--(-GPIO input)
        # Translates the 0V-14.97V --> 0V-3.3V --> digital 0-1023
        #----------------------------------------------------------------------------
        voltage = self.averaged_sample/67.29
        return voltage

    def read_value_text(self, value):
        if value > self.good_fair_threshold:
            return f' {self.good_text} ({value:2.1f})'
        elif value > self.fair_bad_threshold:
            return f' {self.fair_text} ({value:2.1f})'
        return f' {self.bad_text} ({value:2.1f})'

class PhEzo(Sensor):
    def __init__(self, controller, config_file_data):
        super(PhEzo, self).__init__(controller, config_file_data)
        self.current_ph = 6.0
        self.raw_mid = None
        self.raw_high = None
        self.min_max_init(datetime.now())
        self.day_stamp = 0  # Force re-initialization on first sensor read after timezone is avail
        self.log_stamp = datetime.now().hour
        log_path = self.controller.local_phlog_path
        self.ph_logger = logging.getLogger("PhLogger")
        self.ph_logger.setLevel(logging.INFO)
        self.port = int(self.config_info[1].strip())


        try:
            self.ph_ezo = EzoDevice(controller, address=0x63)
        except Exception as e:
            sys.exit(f"Could not create PH monitor thread object. {e}")

        def log_converter(*args):
            return datetime.now(ZoneInfo("UTC")).astimezone(ZoneInfo(self.controller.timezone)).timetuple()

        # Avoid adding multiple log handlers if the class is re-instantiated
        if not self.ph_logger.handlers:
            # Keep 5 backup files, each max 10K
            handler = RotatingFileHandler(log_path, maxBytes=10**4, backupCount=5)
            # Standard CSV-like format: Time,Value
            formatter = logging.Formatter('%(asctime)s,%(message)s', datefmt='%Y-%m-%d %H:%M')
            handler.setFormatter(formatter)

            handler.formatter.converter = log_converter
            self.ph_logger.addHandler(handler)

    def start_thread(self):
        self.ph_ezo.start()

    def terminate_thread(self):
        self.ph_ezo.running = False
        self.ph_ezo.join(timeout=3)
        if self.ph_ezo.is_alive():
            print("Warning: pH ezo thread did not exit gracefully.")
        else:
            print("pH_ezo thread ended gracefully.")

    def read_sensor_and_update(self):
        self.current_ph = self.ph_ezo.get_ph()
        # Do min/max reporting daily
        current_time = self.controller.convert_to_local_time(datetime.now())
        current_day = current_time.day
        if current_day != self.day_stamp:
            # Start a new max/min period of recording
            self.min_max_init(current_time)
            self.day_stamp = current_time.day

        # Record PH in controller for Display Panel
        self.controller.display_ph = self.current_ph

        if self.test_active and not self.controller.maintenance_mode:
            if self.current_ph > self.max_ph:
                self.max_ph = self.current_ph
                self.max_timestamp = current_time
            if self.current_ph < self.min_ph:
                self.min_ph = self.current_ph
                self.min_timestamp = current_time

    def read_value(self):
        return self.current_ph

    def min_max_init(self, current_time):
        self.max_ph = 4
        self.min_ph = 12
        self.max_timestamp = current_time
        self.min_timestamp = current_time

    def log(self, value):
        current_hour = datetime.now().hour
        if current_hour != self.log_stamp:
            # Logging library handles the timestamp and file writing
            self.ph_logger.info(f" {value:2.2f}")
            self.log_stamp = current_hour
            local_file = self.controller.local_phlog_path
            remote_file = self.controller.cloud_phlog_path
            # Write the log file out to the cloud
            self.controller.sync_to_cloud(local_file, remote_file)

    def read_value_text(self, value):
        # need to include the mix/max values/timestamps
        min_ts = self.min_timestamp.strftime("%I:%M %p")
        max_ts = self.max_timestamp.strftime("%I:%M %p")
        return f'{value:2.2f}  max:{self.max_ph:3.2f} at {max_ts}  min:{self.min_ph:3.2f} at {min_ts}'

    def is_port_valid(self):
        return self.port in self.controller.i2c_ports

class Ph4502(GpioAnalog):
    def __init__(self, controller, config_file_data):
        super(Ph4502, self).__init__(controller, config_file_data)
        # This class tracks the max and min values/timestamps and logs PH values every hour
        self.slope = float(self.config_info[5].lstrip())
        self.offset = float(self.config_info[6].lstrip())
        self.samples = deque([(8.1 * self.slope + self.offset)] * 32, maxlen=32)
        self.current_ph = 8.0
        self.raw_low = None
        self.raw_high = None
        self.min_max_init(datetime.now())
        self.day_stamp = 0  # Force re-initialization on first sensor read after timezone is avail
        self.log_stamp = datetime.now().hour
        log_path = self.controller.local_phlog_path
        self.ph_logger = logging.getLogger("PhLogger")
        self.ph_logger.setLevel(logging.INFO)
        self.trim_amount = 4  # Trim 25% from top and bottom of sample buffer

        def log_converter(*args):
            return datetime.now(ZoneInfo("UTC")).astimezone(ZoneInfo(self.controller.timezone)).timetuple()

        # Avoid adding multiple log handlers if the class is re-instantiated
        if not self.ph_logger.handlers:
            # Keep 5 backup files, each max 10K
            handler = RotatingFileHandler(log_path, maxBytes=10**4, backupCount=5)
            # Standard CSV-like format: Time,Value
            formatter = logging.Formatter('%(asctime)s,%(message)s', datefmt='%Y-%m-%d %H:%M')
            handler.setFormatter(formatter)

            handler.formatter.converter = log_converter
            self.ph_logger.addHandler(handler)

    def read_sensor_and_update(self):
        # Use parent class logic to get the trimmed mean
        super().read_sensor_and_update()
        # Record PH in controller for Display Panel
        self.controller.display_ph = self.averaged_sample

        # Debug
        #print(f"{self.samples}\n")

        # Do min/max reporting daily
        current_time = self.controller.convert_to_local_time(datetime.now())
        current_day = current_time.day
        if current_day != self.day_stamp:
            # Start a new max/min period of recording
            self.min_max_init(current_time)
            self.day_stamp = current_time.day

        # Use calibrated slope and offset to convert to PH
        self.current_ph = (self.averaged_sample - self.offset) / self.slope

        # Record PH in controller for Display Panel
        self.controller.display_ph = self.current_ph

        if self.test_active and not self.controller.maintenance_mode:
            if self.current_ph > self.max_ph:
                self.max_ph = self.current_ph
                self.max_timestamp = current_time
            if self.current_ph < self.min_ph:
                self.min_ph = self.current_ph
                self.min_timestamp = current_time

    def read_value(self):
        return self.current_ph

    def min_max_init(self, current_time):
        self.max_ph = 4
        self.min_ph = 12
        self.max_timestamp = current_time
        self.min_timestamp = current_time

    def log(self, value):
        current_hour = datetime.now().hour
        if current_hour != self.log_stamp:
            # Logging library handles the timestamp and file writing
            self.ph_logger.info(f" {value:2.2f}")
            self.log_stamp = current_hour
            local_file = self.controller.local_phlog_path
            remote_file = self.controller.cloud_phlog_path
            # Write the log file out to the cloud
            self.controller.sync_to_cloud(local_file, remote_file)

    def read_value_text(self, value):
        # need to include the mix/max values/timestamps
        min_ts = self.min_timestamp.strftime("%I:%M %p")
        max_ts = self.max_timestamp.strftime("%I:%M %p")
        return f'{value:2.2f}  max:{self.max_ph:3.2f} at {max_ts}  min:{self.min_ph:3.2f} at {min_ts}'

    def calibrate(self, target):
        # Capture the current raw value from the running average
        raw = self.averaged_sample
        if target == self.controller.ph_calibrate_low:
            self.raw_low = raw
        else:
            self.raw_high = raw

        if self.raw_low and self.raw_high:
            self.slope = (self.raw_high - self.raw_low) /  (self.controller.ph_calibrate_high - self.controller.ph_calibrate_low)
            self.offset = self.raw_low - self.controller.ph_calibrate_low * self.slope
            self.save_to_config()
            # Reset the stored calibration data to allow future re-calibration
            self.raw_low = 0
            self.raw_high = 0

    def save_to_config(self):
        filename = self.controller.local_config_path
        remote_filename = self.controller.cloud_config_path
        temp_filename = filename.with_suffix('.tmp')
        backup_filename = filename.with_suffix('.bak')
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

            # Create a backup of the current good config
            shutil.copy2(filename, backup_filename)

            # Write to temporary file first
            with open(temp_filename, 'w') as f:
                f.writelines(updated_lines)
                f.flush()
                os.fsync(f.fileno()) # Force write to physical disk

            # Atomic rename
            os.replace(temp_filename, filename)
            print("Successfully saved new calibration to config.txt")

        except Exception as e:
            print(f"Error saving calibration: {e}")
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

        # Push the updated config to cloud
        self.controller.sync_to_cloud(filename, remote_filename)

    def terminate_thread(self):
        # Method is a no-op for this old version of Ph sensor
        pass

class CalibrationButtons4502:
    def __init__(self, controller):
        self.ph = controller.ph_sensor
        self.controller = controller
        self.btn_mid = Button(25, hold_time=3)
        self.btn_high = Button(27, hold_time=3)

        self.btn_mid.when_held = self._handle_mid_held_button
        self.btn_high.when_held = self._handle_high_held_button

    def _handle_mid_held_button(self):
        if self.controller.maintenance_mode:
            self.ph.calibrate(controller.ph_calibrate_mid)

    def _handle_high_held_button(self):
        if self.controller.maintenance_mode:
            self.ph.calibrate(controller.ph_calibrate_high)

class CalibrationButtonsEzo:
    def __init__(self, controller):
        self.ph_sensor = controller.ph_sensor
        self.controller = controller
        self.btn_mid = Button(25, bounce_time=0.1, hold_time=3)
        self.btn_high = Button(27, bounce_time=0.1, hold_time=3)

        self.btn_mid.when_pressed = self._handle_mid_pressed_button
        self.btn_high.when_pressed = self._handle_high_pressed_button
        self.btn_mid.when_held = self._handle_mid_held_button
        self.btn_high.when_held = self._handle_high_held_button
        self.btn_mid.when_released = self._handle_released_button
        self.btn_high.when_released = self._handle_released_button

    def _handle_high_pressed_button(self):
        if self.controller.maintenance_mode:
            controller.calibrate_text = "Cal HIGH"
            controller.set_calibrate_mode()
            with self.controller.i2c_lock:
                self.controller.update_display()

    def _handle_mid_pressed_button(self):
        if self.controller.maintenance_mode:
            controller.calibrate_text = "Cal MID"
            controller.set_calibrate_mode()
            with self.controller.i2c_lock:
                self.controller.update_display()

    def _handle_high_held_button(self):
        if self.controller.maintenance_mode:
            if self.ph_sensor.ph_ezo.calibrate("high", self.controller.ph_calibrate_high):
                self.controller.calibrate_text = "Success"
            else:
                self.controller.calibrate_text = "Failed"
            with self.controller.i2c_lock:
                self.controller.update_display()

    def _handle_mid_held_button(self):
        if self.controller.maintenance_mode:
            if self.ph_sensor.ph_ezo.calibrate("mid", self.controller.ph_calibrate_mid):
                self.controller.calibrate_text = "Success"
            else:
                self.controller.calibrate_text = "Failed"
            with self.controller.i2c_lock:
                self.controller.update_display()

    def _handle_released_button(self):
        if self.controller.maintenance_mode:
            controller.reset_calibrate_mode()

class MaintenanceModeButton:
    def __init__(self, controller):
        self.controller = controller
        self.btn_maint = Button(12, pull_up=True, bounce_time=0.1, hold_time=3)
        self.btn_maint.when_held = self.controller.set_maintenance
        self.btn_maint.when_released = self.controller.reset_maintenance

class EzoDevice(threading.Thread):
    def __init__(self, controller, address):
        super().__init__()
        self.controller = controller
        self.interface = controller.serial_bus
        self.address = address
        self.current_ph = 8.0
        self.running = True
        self.lock = threading.Lock()
        self.daemon = True

    def run(self):
        while self.running:
            if not self.controller.calibrate_mode:
                self.poll()
            time.sleep(2)

    def poll(self):
        try:
            # Access the underlying smbus object inside luma
            bus = self.interface._bus

            # Send 'R' command (Read)
            with self.controller.i2c_lock:
                bus.write_i2c_block_data(self.address, 0, [ord('R'), ord('\r')])

            # Wait for EZO processing
            time.sleep(1.1)

            # Read 20 bytes from the EZO
            with self.controller.i2c_lock:
                data = bus.read_i2c_block_data(self.address, 0, 20)

            # First byte is the response code (1 = Success)
            if data[0] == 1:
                # Filter out the success code and null bytes
                char_list = [chr(x) for x in data[1:] if x != 0]
                ph_str = "".join(char_list).strip()

                with self.lock:
                    self.current_ph = float(ph_str)
            else:
                print(f"PH Ezo returned bad response code: {data[0]}")
        except Exception as e:
            print(f"Error reading PH EZO. {e}")

    def get_ph(self):
        with self.lock:
            return self.current_ph

    def calibrate(self, point, value):
        """Called by PH_mid and PH_high buttons when in Maintenance Mode"""
        bus = self.interface._bus
        cmd = [ord(c) for c in f"Cal,{point},{value}\r"]
        try:
            with controller.i2c_lock:
                bus.write_i2c_block_data(self.address, 0, cmd)
        except Exception as e:
            print(f"Calibration failed with exception {e}")
            return False
        # Allow time for the hardware to write to EEPROM
        time.sleep(1.3)
        return True

class Control:
    def __init__(self):
        self.my_sensors = []
        self.email_text = []
        self.connected = False
        self.settings_found = []
        self.settings_unexpected = []
        self.settings_missing = []
        self.start_time = datetime.now()
        self.start_time_str = None
        self.display_ph = 0.0
        self.display_temp = 0.0
        self.alarm_active = False
        self.alarm_led_active = False
        self.alarm_text = None
        self.maintenance_mode = False
        self.feed_mode = False
        self.maintenance_start = None
        self.feed_start = None
        self.feed_seconds = None
        self.maintenance_held = False
        self.maintenance_released = None
        self.maintenance_email_sent = False
        self.local_config_path = Path(__file__).parent / 'config.txt'
        self.local_status_path = Path('/tmp/current.txt')
        self.local_override_path = Path('/tmp/override.txt')
        self.local_phlog_path = Path('/tmp/phlog.txt')
        self.saved_phlog_path = Path(Path(__file__).parent / 'logs/phlog.txt')
        self.cloud_status_path = None
        self.cloud_config_path = None
        self.cloud_phlog_path = None
        self.ph_sensor = None
        self.calibrate_text = None
        self.calibrate_mode = False

        # List of required environment variables
        required_vars = {
            'me': 'AQUAMON_EMAIL',
            'email_pw': 'AQUAMON_EMAIL_PW'
        }
        # Mapping config keys to Class names
        self.SENSOR_MAP = {
            'gpioa': GpioAnalog,
            'gpiod': GpioDigital,
            'temp': TempSensor,
            'rflow': RandomFlowSensor,
            'light': LightSensor,
            'floor': FloorWetSensor,
            'hilow': HighLowLevel,
            'battery': Battery,
            'ph': PhEzo,
            'ph4502': Ph4502
        }
        # Configurable integer settings
        self.configurable_integers = [
            'server_update_freq',
            'sample_time',
            'maintenance_timeout',
            'feed_timeout'
        ]

        # Configurable float settings
        self.configurable_floats = [
            'ph_calibrate_mid',
            'ph_calibrate_high'
        ]

        # All required configurable settings
        self.configurable_settings = self.configurable_integers + self.configurable_floats + [
            'smtp',
            'email_subject',
            'cloud_path',
            'cloud_provider',
            'timezone',
            'email_recipients'
        ]

        # Settings allowed to be overridden
        self.allowed_overrides = [
            'ph_calibrate_mid',
            'ph_calibrate_high',
            'server_update_freq',
            'sample_time',
            'email_recipients',
            'maintenance_timeout',
            'feed_timeout'
        ]

        # Supported cloud providers
        self.cloud_providers = [
            'dropbox',
            'onedrive'
        ]

        # Digital INPUT port, GPIO, pin mapping
        self.digital_map = {
            # Monitor port Number, Raspberry PI BCM(GPIO) Number
            '14': DigitalInputDevice(4,  pull_up=True, bounce_time=0.05), # Raspberry pin 7
            '15': DigitalInputDevice(5,  pull_up=True, bounce_time=0.05), # Raspberry pin 29
            '16': DigitalInputDevice(16, pull_up=True, bounce_time=0.05), # Raspberry pin 36
            '17': DigitalInputDevice(17, pull_up=True, bounce_time=0.05), # Raspberry pin 11
            '18': DigitalInputDevice(18, pull_up=True, bounce_time=0.05), # Raspberry pin 12
            '19': DigitalInputDevice(19, pull_up=True, bounce_time=0.05), # Raspberry pin 35
            '20': DigitalInputDevice(20, pull_up=True, bounce_time=0.05), # Raspberry pin 38
            '21': DigitalInputDevice(21, pull_up=True, bounce_time=0.05), # Raspberry pin 40
            '22': DigitalInputDevice(22, pull_up=True, bounce_time=0.05), # Raspberry pin 15
            '23': DigitalInputDevice(23, pull_up=True, bounce_time=0.05)  # Raspberry pin 16
        }
        # Port 24 (GPIO 24) used as output to the remote status LED
        self.external_led = LED(24)  # Raspberry pin 18

        # Analog mapping is a sequential map of port numbers to channels
        #    Monitor port number 1-8 ->  maps to MCP3008 chip 1, channels 0-7
        #    Monitor port number 9-13 -> maps to MCP3008 chip 2, channels 0-4
        #    MCP3008 chip 2 channels 5-7 currently not configured
        self.analog_ports = list(range(1, 14))
        self.digital_ports = list(range(14, 24))
        self.i2c_ports = [25]

        self.i2c_lock = threading.Lock()

        # Create a stop event
        self.stop_event = threading.Event()

        # Register the SIGTERM handler
        signal.signal(signal.SIGTERM, self.handle_shutdown)

        try:
            self.serial_bus = i2c(port=1, address=0x3C)
            self.display = ssd1306(self.serial_bus)
        except:
            self.display = None
            print("OLED not found, continuing without display.")

        # Make sure required env vars are set and exit immediately if not.
        for attr, env_var in required_vars.items():
            value = os.environ.get(env_var)
            if value is None:
                sys.exit(f"Critical Error: {env_var} is not set.")
            setattr(self, attr, value)

        self.load_config(self.local_config_path)

        print(f"Alerts will be sent to the following recipients: {self.email_recipients}")


        # Initialize the maintenance mode switch
        self.maintenance_btn = MaintenanceModeButton(self)

        # Find the Ph object in the list of initialized sensors
        self.ph_sensor = next((x for x in self.my_sensors if isinstance(x, PhEzo)), None)
        # Initialize the Calibration buttons
        if self.ph_sensor:
            self.cal_btns = CalibrationButtonsEzo(self)
            try:
                # Start the PH monitor thread
                self.ph_sensor.start_thread()
            except Exception as e:
                sys.exit(f"Critical Error: Could not start the PH monitor thread. {e}")

        # If no Ph object found, attempt to find the Ph4502 object in the list of initialized sensors
        if not self.ph_sensor:
            self.ph_sensor = next((x for x in self.my_sensors if isinstance(x, Ph4502)), None)
            # Initialize the Calibration buttons for the Ph4502 object
            if self.ph_sensor:
                self.cal_btns = CalibrationButtons4502(self)

        # Initialize SPI Hardware
        try:
            self.spi1 = spidev.SpiDev()
            self.spi1.open(0, 0) # Chip 1 (CE0)
            self.spi1.max_speed_hz = 500000

            self.spi2 = spidev.SpiDev()
            self.spi2.open(0, 1) # Chip 2 (CE1)
            self.spi2.max_speed_hz = 500000
        except Exception as e:
            sys.exit(f"Critical Error: Could not initialize SPI bus. {e}")

        # FreeSans font path
        font_path = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
        self.font_small = ImageFont.truetype(font_path, 12)
        self.font_large = ImageFont.truetype(font_path, 26)
        self.font_medium = ImageFont.truetype(font_path, 16)


        # Initialize starting timeout for maintenance active warning emails
        self.maintenance_delta = self.maintenance_timeout

        # If already switched to maintenance mode during startup, set it.
        if self.maintenance_btn.btn_maint.is_pressed:
            print("Maintenance mode detected during startup!\n")
            self.set_maintenance()

        # Initialize reported calls to force a server update at startup
        self.report_calls = self.server_update_freq / self.sample_time

        # Restore logs kept in tmp from last process termination
        self.restore_logs()

    def handle_shutdown(self, signum, frame):
        print("SIGTERM received. Stopping loop and entering cleanup...")
        self.stop_event.set()

    def cleanup(self):
        # Clean up hardware resources
        try:
            if hasattr(self, 'spi0'):
                self.spi1.close()
            if hasattr(self, 'spi1'):
                self.spi2.close()
            print("SPI buses closed successfully.")
        except Exception as e:
            print(f"Hardware resource cleanup error during termination: {e}")

        # Cleanup the ph_ezo
        if self.ph_sensor:
            self.ph_sensor.terminate_thread()

        # Clear the OLED
        if self.display:
            self.display.clear()
            self.display.cleanup()

        # Save tmp log file for later restore
        try:
            shutil.copy(self.local_phlog_path, self.saved_phlog_path)
            print("Temporary phlog file stored sucessfully.")

        except Exception as e:
            print(f"Saving temp phlog to permanent area failed during termination: {e}")

    def load_config(self, filename):
        with open(filename, 'r') as monitor_config:
            for line in monitor_config:
                # Handle configurable configuration settings
                clean_line = line.strip()
                if not clean_line or clean_line.startswith('#'):
                    continue
                if '=' in clean_line:
                    # Handle configurable settings
                    self.parse_setting(clean_line)
                elif ',' in clean_line:
                    # Handle sensor instantiations
                    parts = [p.strip() for p in clean_line.split(',')]
                    sensor_type = parts[0].strip().lower()

                    # Check if sensor_type matches one of our known sensor types
                    for key, sensor_class in self.SENSOR_MAP.items():
                        if sensor_type == key:
                            self.my_sensors.append(sensor_class(self, parts))
                            break

        if self.settings_unexpected:
            print(f"Warning, unrecognized setting(s) detected: {self.settings_unexpected}")
        self.settings_missing = list(set(self.configurable_settings) - set(self.settings_found))

        if self.settings_missing:
            sys.exit(f'Missing setting(s) in config.txt file: {self.settings_missing}')

        # Check that ports specified in config file are valid for the type of sensor
        for sensor in self.my_sensors:
            if not sensor.is_port_valid():
                sys.exit(f'Configuration error. The specified port ({sensor.config_info[1]}) is not valid for the sensor labeled "{sensor.config_info[3]}"')

        # See if a valid timezone was specified. Expecting a valid IANA name
        valid_zones = available_timezones()
        if self.timezone not in valid_zones:
            print(f"Warning: unknown timezone was specified: {self.timezone}. Defaulting to UTC")
            self.timezone = 'UTC'

        # Test for supported cloud providers
        self.cloud_provider = self.cloud_provider.lower()
        if self.cloud_provider not in self.cloud_providers:
            print(f"Warning: unsupported cloud provider: {self.cloud_provider}.")

        # Define external file paths (can't use Path object for cloud locations)
        cloud_path_sanitized = self.cloud_path.strip('/')
        self.cloud_status_path = f"{self.cloud_provider}:{cloud_path_sanitized}/status/current.txt"
        self.cloud_config_path = f"{self.cloud_provider}:{cloud_path_sanitized}/config.txt"
        self.cloud_phlog_path = f"{self.cloud_provider}:{cloud_path_sanitized}/status/phlog.txt"
        self.cloud_override_path = f"{self.cloud_provider}:{cloud_path_sanitized}/override.txt"

        # Initialize the start time string now that we have the timezone info
        self.start_time_str = self.get_local_timestamp()

        # Look for an override file and apply if needed
        if self.cloud_file_exists(self.cloud_override_path):
            self.load_overrides()

    def load_overrides(self):
        try:
            # We use --quiet to keep the logs clean during normal operation
            subprocess.run(['rclone', 'copyto', self.cloud_override_path, self.local_override_path, '--quiet'], check=True)
            with open(self.local_override_path, 'r') as config_override:
                for line in config_override:
                    # Handle configurable configuration settings
                    clean_line = line.strip()
                    if not clean_line or clean_line.startswith('#'):
                        continue
                    if '=' in clean_line:
                        key, value = line.split('=', 1)
                        if key.strip() in self.allowed_overrides:
                            self.parse_setting(clean_line)
                        else:
                            print(f"Warning, attempt to set a restricted key ({key}) in override file.")
        except Exception as e:
            print(f"Warning: Error processing override file. Exception: {e}")

    def parse_setting(self, line):
        key, value = line.split('=', 1)
        # Use setattr to dynamically assign properties to the class instance
        if key.strip() in self.configurable_integers:
            try:
                value_int = int(value.strip())
            except Exception as error:
                sys.exit(f'Specified value for {key.strip()} must be an integer!')
            setattr(self, key.strip(), value_int)
        elif key.strip() in self.configurable_floats:
            try:
                value_float = float(value.strip())
            except Exception as error:
                sys.exit(f'Specified value for {key.strip()} must be a floating point number!')
            setattr(self, key.strip(), value_float)
        else:
            setattr(self, key.strip(), value.strip())
        if key.strip() in self.configurable_settings:
            self.settings_found.append(key.strip())
        else:
            self.settings_unexpected.append(key.strip())

    def cloud_file_exists(self, remote_path):
        # 'rclone lsjson' returns a JSON list of files.
        # If the file doesn't exist, the file name will not be in the returned list.
        try:
            result = subprocess.run(
                ["rclone", "lsjson", remote_path],
                capture_output=True,
                text=True
            )
        except Exception as e:
            print(f'Error testing for override file. Exception: {e}')
            result = []
        return "override.txt" in result.stdout.strip()

    def convert_to_local_time(self, utc_time):
        local_tz = ZoneInfo(self.timezone)
        local_time = utc_time.astimezone(local_tz)
        return local_time

    def get_local_timestamp(self):
        """Returns a timestamp string in the configured timezone"""
        utc_now = datetime.now(ZoneInfo("UTC"))
        local_now = self.convert_to_local_time(utc_now)
        return local_now.strftime("%A %B %d %I:%M:%S %p")

    def read_analog(self, port_num):
        # Reads raw 0-1023 value from MCP3008 using spidev
        port = int(port_num)

        # Determine which chip and which channel (0-7)
        if port <= 8:
            bus = self.spi1
            channel = port - 1
        else:
            bus = self.spi2
            channel = port - 9  # Ports 9-16 map to channels 0-7 on chip 2

        # Perform SPI transaction
        # [1, (8+channel) << 4, 0] is the standard MCP3008 request pattern
        reply = bus.xfer2([1, (8 + channel) << 4, 0])

        # Construct the 10-bit integer from the 3-byte response
        # (reply[1] & 3) extracts the two 'null/high' bits
        # reply[2] is the remaining 8 bits
        return ((reply[1] & 3) << 8) + reply[2]

    def read_digital(self, port_num):
        label = str(port_num).strip()
        if label in self.digital_map:
            return 0 if self.digital_map[label].is_active else 1
        return 1

    def set_alarm_led(self):
        self.external_led.blink(on_time=0.5, off_time=0.5)

    def set_maintenance_led(self):
        self.external_led.on()

    def set_feed_led(self):
        self.external_led.blink(on_time=1.0, off_time=0.5)

    def reset_alarm_led(self):
        self.external_led.off()

    def reset_maintenance_led(self):
        self.external_led.off()

    def reset_feed_led(self):
        self.external_led.off()

    def update_display(self):
        with canvas(self.display) as draw:
            if self.display:
                line1 = f"Time: {self.convert_to_local_time(datetime.now()).strftime('%H:%M:%S')}"
                draw.text((0, 0), line1, font=self.font_medium, fill="white")
                if self.alarm_led_active and not self.maintenance_mode:
                    line2 = "Alert Active!"
                    line3 = f"{self.alarm_text}"
                    draw.text((0, 20), line2, font=self.font_large, fill="white")
                    draw.text((0, 44), line3, font=self.font_medium, fill="white")
                elif self.calibrate_mode:
                    line2 = self.calibrate_text
                    line3 = f"PH:   {self.display_ph:.2f}"
                    draw.text((0, 20), line2, font=self.font_large, fill="white")
                    draw.text((0, 42), line3, font=self.font_large, fill="white")
                elif self.maintenance_mode:
                    line2 = "Maintenance"
                    line3 = f"PH:   {self.display_ph:.2f}"
                    draw.text((0, 20), line2, font=self.font_large, fill="white")
                    draw.text((0, 42), line3, font=self.font_large, fill="white")
                elif self.feed_mode:
                    line2 = "Feed Mode"
                    minutes, seconds = divmod(self.feed_seconds, 60)
                    line3 = f"Countdown: {minutes:02d}:{seconds:02d}"
                    draw.text((0, 20), line2, font=self.font_large, fill="white")
                    draw.text((0, 42), line3, font=self.font_medium, fill="white")
                else:
                    line2 = f"Temp: {self.display_temp:.1f} F"
                    line3 = f"PH:   {self.display_ph:.2f}"
                    draw.text((0, 20), line2, font=self.font_large, fill="white")
                    draw.text((0, 42), line3, font=self.font_large, fill="white")

    def read_sensors_and_update(self):
        for x in self.my_sensors:
            x.read_sensor_and_update()

    def send_email_alert(self):
        outer = MIMEMultipart()
        outer['Subject'] = self.email_subject
        outer['From'] = self.me
        outer['To'] = self.email_recipients
        # Add the alert message
        msg = MIMEText("\n".join(self.email_text))
        outer.attach(msg)

        # Path to current status
        status_file = self.local_status_path

        # Attach the current status information
        try:
            contents = status_file.read_text()
            stats = MIMEText(contents.replace(';', '\n'))
            outer.attach(stats)
        except FileNotFoundError:
            print("Warning: current.txt not found for email attachment.")

        # Add a link to check the current status
        email_link = MIMEText(f"{self.cloud_status_path}\n")
        outer.attach(email_link)

        # Send the email
        try:
            with smtplib.SMTP(self.smtp, 587) as server:
                server.ehlo()
                server.starttls()
                server.login(self.me, self.email_pw)
                server.sendmail(self.me, self.email_recipients.split(','), outer.as_string())
        except Exception as error:
            print(f"Exception={error} Error sending alert!: {msg}")
        # Initialize for next alert
        self.email_text[:] = []

    def test_and_report(self):

        self.report_calls += 1
        for sensor in self.my_sensors:
            sensor_current_values = [sensor.test() for sensor in self.my_sensors]
        # If there was an alarm active after this round of sampling, set the led alarm
        if self.alarm_active:
            self.set_alarm_led()
            self.alarm_led_active = True
            self.alarm_active = False
        else:
            if self.alarm_led_active:
                self.reset_alarm_led()
                self.alarm_led_active = False
        # Test for an extended maintenance mode. May have been left on accidentally
        self.test_long_maintenance_mode()
        # Test for feed timeout
        self.test_feed_timeout()

        if (self.report_calls * self.sample_time) > self.server_update_freq or self.email_text:
            self.report_calls = 0
            cur_date_time = self.get_local_timestamp()
            status_file_path = self.local_status_path
            with status_file_path.open('w') as status_file:
                status_file.write(f'Sample time: {cur_date_time}\n')
                status_file.write(f'Monitor start time: {self.start_time_str}\n')

                for sensor, current_val in zip(self.my_sensors, sensor_current_values):
                    status_file.write(f'{sensor.read_label()}:{sensor.read_value_text(current_val)}\n')
                    try:
                        sensor.log(current_val)
                    except Exception as logerr:
                        print(f"Exception={logerr} Error making log entry for {sensor.read_label()}!")
            if self.email_text:
                alerts = ", ".join(self.email_text)
                clean_alerts = alerts.replace("\n", "")
                print(f"{cur_date_time}: {clean_alerts}")
                self.send_email_alert()

            self.sync_to_cloud(self.local_status_path, self.cloud_status_path)

    def sync_to_cloud(self, local_file, remote_dest):
        """Uploads status to cloud using the rclone API"""

        try:
            # We use --quiet to keep the logs clean during normal operation
            subprocess.run(['rclone', 'copyto', local_file, remote_dest, '--quiet'], check=True)
            # print("Cloud sync successful.") # Uncomment for debugging
        except subprocess.CalledProcessError as e:
            # Internet likely down if we reach here.
            print(f"Cloud Sync to {remote_dest} Failed : {e}")

    def set_maintenance(self):
        if self.feed_mode:
            self.reset_feed_mode()
        self.maintenance_held = True
        self.maintenance_mode = True
        self.set_maintenance_led()
        self.maintenance_start = datetime.now()

    def reset_maintenance(self):
        # If the button was held for 'hold_time' seconds, we must now reset maintenance mode
        # otherwise we assume the feed mode button was pressed, so we set feed mode.
        if self.maintenance_held:
            self.maintenance_held = False # Reset for next time
            self.maintenance_mode = False
            self.reset_maintenance_led()
            # reset any partial PH calibration actions
            self.ph_sensor.raw_mid = None
            self.ph_sensor.raw_high = None
        else:
            self.feed_mode = True
            self.set_feed_led()
            self.feed_start = datetime.now()

    def reset_feed_mode(self):
        self.feed_mode = False
        self.reset_feed_led()

    def test_feed_timeout(self):
        if self.feed_mode:
            feed_time_remaining = self.feed_start + timedelta(minutes=self.feed_timeout) - datetime.now()
            self.feed_seconds = int(feed_time_remaining.total_seconds())
            if self.feed_seconds < 0:
                self.reset_feed_mode()

    def test_long_maintenance_mode(self):
        if self.maintenance_mode and self.maintenance_start + timedelta(minutes=self.maintenance_delta) < datetime.now():
            self.email_text.append(f"Warning: maintenance mode active for {self.maintenance_delta} minute(s)\n")
            self.maintenance_email_sent = True
            self.maintenance_delta += self.maintenance_timeout
        elif self.maintenance_email_sent and not self.maintenance_mode:
            self.email_text.append("Maintenance mode is no longer active. Alerts re-enabled\n")
            self.maintenance_email_sent = False
            self.maintenance_delta = self.maintenance_timeout

    def set_calibrate_mode(self):
        self.calibrate_mode = True

    def reset_calibrate_mode(self):
        self.calibrate_mode = False

    def restore_logs(self):
        if os.path.exists(self.saved_phlog_path):
            shutil.copy(self.saved_phlog_path, self.local_phlog_path)
            # Clear it so we don't keep restoring old data
            os.remove(self.saved_phlog_path)

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
    controller = Control()
    while True:
        try:
            controller.read_sensors_and_update()
            controller.test_and_report()
            with controller.i2c_lock:
                controller.update_display()
            if controller.stop_event.wait(controller.sample_time):
                break
        except KeyboardInterrupt:
            print("\nUser requested termination. Exiting.")
            break
        except Exception as error:
            print("Unhandled Exception! Exiting")
            print("--- Stack Trace Start ---")
            traceback.print_exc()
            print("--- Stack Trace End ---")
            break
    controller.cleanup()

if __name__ == '__main__':
    main()

