#!/usr/bin/env python3

# Script to monitor reef aquarium

import sys
import os
import shutil
import time
import telnetlib
import math
import smtplib
from pathlib import Path
from datetime import timedelta, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from collections import deque

class Gpio:
    def __init__(self, gpio_controller, config_file_data):
        self.controller = gpio_controller
        self.config_info = config_file_data
        # Initialize very old time
        self.last_sent_alert = datetime.now() - timedelta(days=356)
        self.nag_level = self.config_info[2].lstrip()
        self.test_active = False

    def read_value(self):
        # Needs to be implemented in the derived classes
        raise NotImplementedError

    def test(self):
        current_value = self.read_value()
        if self.test_active == False:
            if current_value < 0 or self.controller.start_time + timedelta(seconds=90) > datetime.now():
                return current_value
        self.test_active = True
        if self.controller.calibrate == True:
            return current_value
        conditions = self.config_info[4].lstrip().split('+')
        for condition in conditions:
            if ':' in condition:
                time_value = condition.split('=')
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
                    if (self.last_sent_alert + timedelta(hours=int(self.nag_level))) < datetime.now():
                        self.controller.email_text.append('{} Alert!\n'.format(self.read_label()))
                        self.last_sent_alert = datetime.now()
                        # force a server update prior to sending the alarm
                        self.controller.report_calls = int(self.controller.server_update_freq) / int(self.controller.sample_time)

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
        return 'range:' + self.config_info[4].strip()

    def read_value_text(self, value):
        return '{0:6.1f}'.format(value)

    def read_sensor_and_update(self):
         # Simply append; the oldest value is dropped automatically  
        new_val = self.controller.read_analog(self.config_info[1].lstrip())
        self.samples.append(new_val)
        # Create a running averaged sample dumping the 1/4th highest and 1/4th lowest samples
        if self.enable_averaging == True:
            temp_samples = sorted(list(self.samples))
            # Trim 25% lowest and 25% highest
            trim_low = int(len(temp_samples)/4)
            trim_high = int(len(temp_samples)) - trim_low
            temp_samples = temp_samples[trim_low:trim_high]

            self.averaged_sample = sum(temp_samples) / len(temp_samples)

    def isDigital(self):
        return False;

    def isAnalog(self):
        return True;

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

    def isDigital(self):
        return True

    def isAnalog(self):
        return False

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
            retval = self.config_info[5].strip() + ' {:.0f} minutes.'.format(minutes_on)
        elif self.ones_count > 0:
            minutes_off = (self.ones_count * self.controller.sample_time)/60
            retval = self.config_info[6].strip() + ' {:.0f} minutes.'.format(minutes_off)
        else:
            return 'Not Avail'
        percent_on = (self.zeros_total * 100) / (self.zeros_total + self.ones_total)
        return retval + ' (overall on-time: {:.0f}%)'.format(percent_on)

class TempSensor(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(TempSensor, self).__init__(gpio_controller, config_file_data)

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
        temp = math.log(resistance)
        temp = 1 / (0.001129148 + (0.000234125 * temp) + (0.0000000876741 * temp * temp * temp))
        #Convert from Kelvin the Celsius
        temp = temp - 273.15
        # Convert to Fahrenheit.
        temp = (temp * 9.0) / 5.0 + 32.0
        # Adjust with calibration value
        calibration = float(self.config_info[6].lstrip())

        return temp + calibration

class RandomFlowSensor(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(RandomFlowSensor, self).__init__(gpio_controller, config_file_data, False)
        # set the sample buffer to 128 entries
        self.samples = deque(range(0,1024,8), maxlen=128)

    def read_value(self):
        # Convert the sample data into a standard deviation
        mean = sum(self.samples) / len(self.samples)
        sumOfSquares = 0.0
        for sample in self.samples:
            sumOfSquares += pow((sample - mean), 2)
        std_dev = math.sqrt(sumOfSquares / len(self.samples))
        return std_dev

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
        if self.controller.calibrate == True:
            print('Battery raw digital: {}'.format(self.averaged_sample))
            return self.averaged_sample
        voltage = self.averaged_sample/68.31
        return voltage
        
    def read_value_text(self, value):
        if value > float(self.config_info[5].strip()):
            return ' {0} ({1:2.1f})'.format(self.config_info[6].strip(), value)
        elif value > float(self.config_info[7].strip()):
            return ' {0} ({1:2.1f})'.format(self.config_info[8].strip(), value)
        return ' {0} ({1:2.1f})'.format(self.config_info[9].strip(), value)
            
class Ph(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(Ph, self).__init__(gpio_controller, config_file_data)
        # This class tracks the max and min values/timestamps and logs PH values every hour
        self.slope = float(self.config_info[5].lstrip())
        self.offset = float(self.config_info[6].lstrip())     
        # set the sample buffer to 36 entries,initialized at a ph of 8.
        self.samples = deque([(8 - self.offset) * self.slope] * 36, maxlen=36)
        self.min_max_init()
        self.log_stamp = datetime.now().hour

    def read_value(self):
        current_day = datetime.now().day
        if current_day != self.day_stamp:
            # Start a new max/min period of recording
            self.min_max_init()
        #print(self.samples)
        if self.controller.calibrate == True:
            print('PH raw digitial: {}'.format(self.averaged_sample))
            return self.averaged_sample
        ph = self.averaged_sample / self.slope + self.offset
        if self.test_active == True:         
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
            # write current datetime and PH value into the log file
            with open(self.controller.local_filepath + self.controller.cloud_store + 'phlog.txt', 'a') as ph_log:
                curDateTimeRaw = datetime.now()
                curDateTime = curDateTimeRaw.strftime("%Y-%m-%d %H:%M:%S")
                ph_log.write('{0},{1:2.1f}\n'.format(curDateTime, value))
            self.log_stamp = current_hour
        
    def read_value_text(self, value):
        # need to include the mix/max values/timestamps
        min_ts = self.min_timestamp.strftime("%I:%M %p")
        max_ts = self.max_timestamp.strftime("%I:%M %p")
        return '{0:2.1f}  max:{1:3.1f} at {2}  min:{3:3.1f} at {4}'.format(value, self.max_ph, max_ts, self.min_ph, min_ts)


class GpioCtl:
    def __init__(self):
        self.my_gpios = []
        self.email_text = [] 
        self.connected = False
        self.start_time = datetime.now()
        self.start_time_str = self.start_time.strftime("%A %B %d %I:%M:%S %p")
        
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

        self.calibrate = len(sys.argv) > 1 and sys.argv[1] == 'Calibrate'
        self.load_config('config.txt')
        # Initialize reported calls to force a server update at startup
        self.report_calls = int(self.server_update_freq) / int(self.sample_time)
        # Connect to the GPIO monitor
        self.connect()

    def load_config(self, filename):
        with open(filename, 'r') as gpio_config:
            for line in gpio_config:
                line = line.strip()
                if not line or line[0] == '#' or '=' in line:
                    # Handle global settings (username, password, etc.)
                    if '=' in line:
                        self.parse_setting(line)
                    continue
                
                # Handle sensor instantiations
                parts = line.split(',')
                prefix = parts[0].lower()
                
                # Check if the prefix matches one of our known sensor types
                for key, sensor_class in self.SENSOR_MAP.items():
                    if prefix.startswith(key):
                        self.my_gpios.append(sensor_class(self, parts))
                        break

    def parse_setting(self, line):
        key, value = line.split('=', 1)
        # Use setattr to dynamically assign properties to the class instance
        setattr(self, key.strip(), value.strip())

    def authenticate(self):
        self.tn.read_until('User Name: '.encode(),int(self.connect_timeout))
        self.tn.write((self.username + '\n').encode())
        self.tn.read_until('Password: '.encode(), int(self.connect_timeout))
        self.tn.write((self.password  + '\n').encode())
        print((self.tn.read_until('>>'.encode())).decode())
        self.connected = True

    def connect(self):
        self.tn = telnetlib.Telnet(self.tcp_addr)
        self.authenticate()

    def attempt_reconnect(self):
        attempt = 1
        while attempt < int(self.reconnect_attempts):
            dt_string = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
            print("{} Attempt reconnect in {} seconds...".format(dt_string, self.reconnect_delay))
            time.sleep(int(self.reconnect_delay))
            try:
                self.tn.open(self.tcp_addr)
                self.authenticate()
                break
            except Exception as error:
                print("Attempt number {} failed".format(attempt))
                attempt += 1
                if attempt == self.reconnect_attempts:
                    print("Could not reconnect after {} attempts Terminating.".format(attempt))
                    raise
                self.tn.close()
                self.connected = False
        print("Successfully reconnected after {} attempts :)".format(attempt))

    def disconnect(self):
        try:
            self.tn.write('exit\n'.encode())
        except Exception as error:
            print("Ignored Exception={} attempting to disconnect".format(error))

    def read_gpio(self, read_type, gpio_num):
        while True:
            try:
                self.tn.write((read_type + ' {} \n'.format(gpio_num)).encode())
                result = self.tn.read_until('>'.encode(), int(self.connect_timeout)).decode()
                rtn_int = int(result.split()[0])
                break
            except Exception as error:
                print("Lost connection. Exception={} reading GPIO!".format(error))
                self.tn.close()
                self.connected = False
                self.attempt_reconnect()              
        return rtn_int

    def read_analog(self, gpio_num):
        return self.read_gpio('adc read', gpio_num)

    def read_digital(self, gpio_num):
        return self.read_gpio('gpio read', gpio_num)

    def read_sensors_and_update(self):
        for x in self.my_gpios:
            x.read_sensor_and_update()

    def send_email_alert(self):
        me = os.environ.get('AQUAMON_EMAIL')
        password = os.environ.get('AQUAMON_EMAIL_PW')
        recipients = os.environ.get('AQUAMON_RECIPIENTS').split(',')
        outer = MIMEMultipart()
        outer['Subject'] = self.email_subject
        outer['From'] = me
        outer['To'] = ','.join(recipients)
        # Add the alert message
        msg = MIMEText("\n".join(self.email_text))
        outer.attach(msg)

        # Attach the current status information
        with open(self.local_filepath + self.cloud_store + 'current.txt', 'r') as sf:
            contents = sf.read()
            stats = MIMEText(contents.replace(';', '\n'))
        outer.attach(stats)

        # Add a link to check the current status
        email_link = MIMEText(self.cloud_store + 'current.txt\n')
        outer.attach(email_link)
      
        # Send the email
        try:
            with smtplib.SMTP(self.smtp, 587) as server:
                server.connect(self.smtp, 587)
                server.ehlo()
                server.starttls()
                server.login(me, password)
                server.sendmail(me, recipients, outer.as_string())
        except Exception as error:
            print("Exception={} Error sending alert!: {}".format(error, msg))
        # Initialize for next alert
        self.email_text[:] = []

    def test_and_report(self):
        # store the status file to the cloud drive based on the update frequency
        self.report_calls += 1
        if (self.report_calls * int(self.sample_time)) > int(self.server_update_freq) or self.email_text:
            self.report_calls = 0
            with open(self.local_filepath + self.cloud_store + 'current.txt', 'w') as status_file:
                curDateTimeRaw = datetime.now()
                curDateTime = curDateTimeRaw.strftime("%A %B %d %I:%M:%S %p")
                status_file.write('Sample time: {}\n'.format(curDateTime))
                status_file.write('Monitor start time: {}\n'.format(self.start_time_str))
                for gpio in self.my_gpios:
                    current_value = gpio.test()
                    status_file.write('{0}:{1}\n'.format(gpio.read_label(), gpio.read_value_text(current_value)))
                    try:
                        gpio.log(current_value)
                    except Exception as logerr:
                        print("Exception={} Error making log entry for {}!".format(logerr,gpio.read_label()))
        if self.email_text:
            self.send_email_alert()

def main():
    controller = GpioCtl()
    while True:
        try:
            controller.read_sensors_and_update()
            controller.test_and_report()
            time.sleep(int(controller.sample_time))
        except KeyboardInterrupt:
            print("User requested termination. Exiting.")
            break
        except Exception as error:
            print("Exception={} Unhandled! Exiting".format(error))
            raise
    controller.disconnect()


if __name__ == '__main__':
    main()

