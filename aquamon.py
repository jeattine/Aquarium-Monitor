#!/usr/bin/env python3

# Script to monitor reef aquarium

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
                        self.controller.report_calls = self.controller.server_update_freq / self.controller.sample_time

        return current_value

    def in_time_range(self, time_start, time_end):
        startTime = datetime.strptime(time_start,"%H:%M")
        endTime = datetime.strptime(time_end,"%H:%M")
        if startTime > endTime:
            endAdjust = 1
        else:
            endAdjust = 0
        curDateTime = datetime.now();
        tomorrowDateTime = curDateTime + timedelta(days=1)
        startDateTime = datetime.combine(curDateTime.date(), startTime.time())
        endDateTime = datetime.combine(curDateTime.date(), endTime.time()) + timedelta(days=endAdjust)
        if startDateTime < curDateTime < endDateTime:
            inTimeRange = 1
        elif startDateTime < tomorrowDateTime < endDateTime:
            inTimeRange = 1
        else:
            inTimeRange = 0
        return inTimeRange

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
        self.samples= list(range(0,1024,64))

    def read_value(self):
        return self.averaged_sample

    def read_condition(self):
        return 'range:' + self.config_info[4].strip()

    def read_value_text(self, value):
        return '{0:6.1f}'.format(value)

    def read_sensor_and_update(self):
        self.samples = self.samples[1:]
        self.samples.append(self.controller.read_analog(self.config_info[1].lstrip()))
        # Create a running averaged sample dumping the 1/4th highest and 1/4th lowest samples
        if self.enable_averaging == True:
            temp_samples = self.samples[:]
            temp_samples.sort()
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
        # extend the sample buffer from 16 entries to 118 entries
        self.samples.extend(range(0,1024,10))

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

class Ph(GpioAnalog):
    def __init__(self, gpio_controller, config_file_data):
        super(Ph, self).__init__(gpio_controller, config_file_data)
        # This class tracks the max and min values/timestamps and logs PH values every hour
        # extend the sample buffer from 16 entries to 118 entries
        self.samples[:] = [472.5] * (len(self.samples) + 20)
        self.min_max_init()
        self.log_stamp = datetime.now().hour
        self.slope = float(self.config_info[5].lstrip())
        self.offset = float(self.config_info[6].lstrip())      

    def read_value(self):
        current_day = datetime.now().day
        if current_day != self.day_stamp:
            # Start a new max/min period of recording
            self.min_max_init()
        #print(self.samples)
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
            with open(self.controller.cloud_store + 'phlog.txt', 'a') as ph_log:
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
        # List of gpio objects indexed by gpio number
        self.my_gpios = []
        self.email_text = [] 
        self.connected = False
        self.start_time = datetime.now()
        self.start_time_str = self.start_time.strftime("%A %B %d %I:%M:%S %p")
        with open('config.txt', 'r') as gpio_config:
            for line in gpio_config:
                # Start of sensor object instantiations
                if 'gpioa' in line[:5]:
                    parts = line.split(',')
                    # Create analog gpio object and add to  list
                    self.my_gpios.append(GpioAnalog(self, parts))
                elif 'gpiod' in line[:5]:
                    parts = line.split(',')
                    # Create digital gpio object and add to  list
                    self.my_gpios.append(GpioDigital(self, parts))
                elif 'temp' in line[:4]:
                    parts = line.split(',')
                    # Create temperature object and add to  list
                    self.my_gpios.append(TempSensor(self, parts))
                elif 'rflow' in line[:5]:
                    parts = line.split(',')
                    # Create flow object and add to  list
                    self.my_gpios.append(RandomFlowSensor(self, parts))
                elif 'flow' in line[:4]:
                    parts = line.split(',')
                    # Create flow object and add to  list
                    self.my_gpios.append(FlowSensorFX4(self, parts))
                elif 'light' in line[:5]:
                    parts = line.split(',')
                    # Create light object and add to  list
                    self.my_gpios.append(LightSensor(self, parts))
                elif 'floor' in line[:5]:
                    parts = line.split(',')
                    # Create floor wet object and add to  list
                    self.my_gpios.append(FloorWetSensor(self, parts))
                elif 'co2' in line[:3]:
                    parts = line.split(',')
                    # Create CO2 delivery object and add to  list
                    self.my_gpios.append(CO2deliverySensor(self, parts))
                elif 'hilow' in line[:5]:
                    parts = line.split(',')
                    # Create High Low water level object and add to  list
                    self.my_gpios.append(HighLowLevel(self, parts))
                elif 'ph' in line[:2]:
                    parts = line.split(',')
                    # Create PH object and add to  list
                    self.my_gpios.append(Ph(self, parts))
                # End of Sensor Object instantiations
                elif 'username' in line[:8]:
                    parts = line.split('=')
                    self.username = parts[1].rstrip()
                elif 'password' in line[:8]:
                    parts = line.split('=')
                    self.password = parts[1].rstrip()
                elif 'tcpip' in line[:5]:
                    parts = line.split('=')
                    self.tcp_addr = parts[1].rstrip()
                elif 'smtp' in line[:4]:
                    parts = line.split('=')
                    self.smtp = parts[1].rstrip()
                elif 'notify' in line[:6]:
                    parts = line.split('=')
                    self.notify = parts[1].rstrip()
                elif 'stats_file' in line[:10]:
                    parts = line.split('=')
                    self.stats_file = parts[1].rstrip()
                elif 'connect_timeout' in line[:15]:
                    parts = line.split('=')
                    self.timeout = int(parts[1].rstrip())
                elif 'reconnect_delay' in line[:15]:
                    parts = line.split('=')
                    self.reconnect_delay = int(parts[1].rstrip())
                elif 'reconnect_attempts' in line[:18]:
                    parts = line.split('=')
                    self.reconnect_attempts = int(parts[1].rstrip())
                elif 'server_update_freq' in line[:18]:
                    parts = line.split('=')
                    self.server_update_freq = int(parts[1].rstrip())
                elif 'sample_time' in line[:11]:
                    parts = line.split('=')
                    self.sample_time = int(parts[1].rstrip())                  
                elif 'email_subject' in line[:13]:
                    parts = line.split('=')
                    self.email_subject = parts[1].rstrip()
                elif 'email_from' in line[:10]:
                    parts = line.split('=')
                    self.email_from = parts[1].rstrip()
                elif 'cloud_store' in line[:11]:
                    parts = line.split('=')
                    self.cloud_store = parts[1].rstrip()

        # Initialize reported calls to force a server update at startup
        self.report_calls = self.server_update_freq / self.sample_time
        # Connect to the GPIO monitor
        self.connect()

    def authenticate(self):
        self.tn.read_until('User Name: '.encode(),self.timeout)
        self.tn.write((self.username + '\n').encode())
        self.tn.read_until('Password: '.encode(), self.timeout)
        self.tn.write((self.password  + '\n').encode())
        print((self.tn.read_until('>>'.encode())).decode())
        self.connected = True

    def connect(self):
        self.tn = telnetlib.Telnet(self.tcp_addr)
        self.authenticate()

    def attempt_reconnect(self):
        attempt = 1
        while attempt < self.reconnect_attempts:
            dt_string = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
            print("{} Attempt reconnect in {} seconds...".format(dt_string, self.reconnect_delay))
            time.sleep(self.reconnect_delay)
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
                result = self.tn.read_until('>'.encode(), self.timeout).decode()
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
        if self.email_text:
            me = self.email_from
            outer = MIMEMultipart()
            outer['Subject'] = self.email_subject
            outer['From'] = me
            outer['To'] = self.notify
            # Add the alert message
            msg = MIMEText("\n".join(self.email_text))
            outer.attach(msg)

            # Attach the current status information
            with open(self.stats_file, 'r') as sf:
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
                    server.login(me, "abcdefghijklmnop")
                    recipients = self.notify.split(',')
                    server.sendmail(me, recipients, outer.as_string())
            except Exception as error:
                print("Exception={} Error sending alert!: {}".format(error, msg))
            # Initialize for next alert
            self.email_text[:] = []

    def test_and_report(self):
        with open(self.stats_file, 'w') as status_file:
            curDateTimeRaw = datetime.now()
            curDateTime = curDateTimeRaw.strftime("%A %B %d %I:%M:%S %p")
            status_file.write('Monitor start time: {}\n'.format(self.start_time_str))
            status_file.write('Sample time: {}\n'.format(curDateTime))
            for gpio in self.my_gpios:
                current_value = gpio.test()
                status_file.write('{0}:{1}\n'.format(gpio.read_label(), gpio.read_value_text(current_value)))
                try:
                    gpio.log(current_value)
                except Exception as logerr:
                    print("Exception={} Error making log entry for {}!".format(logerr,gpio.read_label()))
        # store the status file to the cloud drive based on the update frequency
        self.report_calls += 1
        if (self.report_calls * self.sample_time) > self.server_update_freq:
            self.report_calls = 0
            try:
                shutil.copyfile(self.stats_file, self.cloud_store + 'current.txt')
            except Exception as error:
                print("Exception={} Error updating cloud drive!".format(error))
        self.send_email_alert()

def main():
    controller = GpioCtl()
    while True:
        try:
            controller.read_sensors_and_update()
            controller.test_and_report()
            time.sleep(controller.sample_time)
        except KeyboardInterrupt:
            print("User requested termination. Exiting.")
            break
        except Exception as error:
            print("Exception={} Unhandled! Exiting".format(error))
            raise
    controller.disconnect()


if __name__ == '__main__':
    main()

