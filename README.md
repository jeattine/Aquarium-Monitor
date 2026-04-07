
# Aquarium monitor

![Assembled3](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/assembled3.jpg)

Python-based aquarium monitor program running under the Raspberry Pi OS Lite Linux operating system on a Raspberry Pi 4 board. A Adafruit Perma-Proto Hat is mounted on the board to house two MCP3008 10-bit ADC with SPI interface. This provides the analog inputs to the monitor. The HAT also provides solder pads for each of the other GPIO pins used as digital inputs. The monitor has 23 RCA sockets for input of the sensors. One RCA socket is used for output for the alarm/maintenance_mode LED indicator. The monitor has a button to force a reset or a shutdown of the OS/monitor. The monitor provides two buttons for the calibration of the PH probe, with a PH-Low and a PH-High that can be set to the values of the calibration fluid in the configuration file or the override file. The calibration action will write its result back the configuration file. The monitor status, PH logs, and updated configuration files can be observed in a cloud folder (I am using Dropbox) by external devices. This is accomplished using 'rclone copyto'. Monitor alerts are surfaced by emails sent to the recipients listed in the configuration file. The monitor will autostart after the Linux OS boots. It is started via a service and set to be restarted if it abnormally terminates. There is a maintenance mode switch on the front that when activated, alarms are disabled and the red LED light will turn on. In this mode the display will show Maintenance text along with the current PH value. The PH value display is helpful during PH calibration so that it can be seen that the PH values have stabilized with the probe in the calibration fluid.

The program design has a 'Main' that constructs an GpioCtl object and loops calling methods on the GpioCtl object instantiation. 'Main' will stay in a continuous loop until an exception causes it to exit. The input to the program is a config.txt file expected to be in the current directory. This file is composed of two sections. The first section assigns the port numbers of the hardware to various classes to read and process the sensor data connected to those port inputs. Some examples are classes to monitor temperature, PH, Flow, water level, and light. These classes are derived from either a GPIO_Digital or a GPIO_Analog class, depending on the type of sensor. The GPIO_Digital and GPIO_Analog are derived from the GPIO base class. In addition to the GPIO assignment to classes, this section of the config file also gives a descriptive name to each port input and defines the expected values/ranges/time-periods for operation. Another input to the program is the override.txt file. This file resides at a cloud location, either Dropbox or Onedrive depending on how the system is configured. This override file provides a convenient way to modify a subset of the settings in the config.txt file. For example when going on vacation I may want to modify the recipient list of the email alerts. I can do this by simply modifying the override file in the cloud folder from any device that has access to that folder. The utility Tailscale is installed on the monitor and on personal devices that then have direct ssh access to the monitor. This sets up a split VPN tunnel directly between the personal devices and the monitor, allowing safe client SSH access to the monitor from outside the local home network. This is useful if I need to perform a more drastic administrative or service action when away from home. When away from my primary laptop, the need may arise to modify the config.txt or the aquamon.py file. My IPAD and phone both have a dropbox application and Tailscale to create the VPN tunnel. On the IPAD I am using the Terminal# app which will get me into an SSH session. On the phone I use Termux. On the monitor I have two aliases set up: update-aquamon and update_config. They will use 'rclone copyto' to copy files from my local GitHub repository located in dropbox to the monitor. From there a systemctl restart put the new files in play. For an editor on the ipad I am using Runestone. It's simple, lightweight, and color-codes nicely editing python code.

Code structure:

![Class structure](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/Design2.png)

![Class structure](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/ExampleOutput.png)

This is the bigger picture, showing the network interfaces and wiring to the various sensors:
![Summary](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/Summary.png)

The Raspberry Pi board, Perma-Proto Hat with the two MCP3008 ICs, and the wiring to the RCA inputs:

![Internals](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/internal.jpg)

![Assembled2](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/assembled2.jpg)

![Assembled1](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/assembled1.jpg)

Internal wiring schematic:

![Schematic](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/schematic.png)

The following images show the various sensors that feed the monitor through the RCA ports:


![Flow Detection](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/FlowDetect.png)
![Hi Low Level Detection](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/HiLowDetect.png)
![Random Flow Detect](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/RandomFlowDetect.png)
![Misc Detect](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/VariousDetect.png)
![Conditional and Temp Detect](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/ConditionalTempDetect.png)
![Battery Condition](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/BatteryCondition.png)
![PH Detect page 1](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/PhDetect.png)
![Filter Roller](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/Filterroller.png)

## Raspberry Pi Setup for the Aquarium Monitor

### Flash the OS

1.  Download the **Raspberry Pi Imager** on your Windows 11 machine.
2.  Select **OS**: _Raspberry Pi OS (64-bit) Lite_ (You don't need a desktop GUI).
3.  Select **Storage**: Your microSD card.
4.  **Gear Icon (Edit Settings)**:
    *   **Set hostname:** e.g., aquamon-local
    *   **Set username/password:** (e.g., pi and your chosen password).
    *   **Configure Wireless LAN:** Enter your SSID and Password.
    *   **Services Tab:** Check **Enable SSH** and use password authentication.
5.  Click **Write**.

### Connect via SSH

Once the card is flashed, pop it into the Pi and power it up. Wait about 2 minutes for the first boot.

1.  Open **PowerShell** on Windows 11.
2.  Type: ssh pi@aquamon.local (replace pi and aquamon with the credentials you set).
3.  If it asks about "authenticity of host," type yes.
4.  Enter your password. You are now "inside" the Pi.
5.  Finish and Reboot: sudo reboot. (You'll be disconnected; wait a minute and SSH back in).

### Environment Setup and Libraries

Modern Raspberry Pi OS (Bookworm) requires a **Virtual Environment (venv)** to prevent breaking system-wide packages.

**\# Update the system**

sudo apt update sudo apt upgrade -y  
sudo apt install python3-dev -y  
sudo apt install i2c-tools -y  
sudo apt install rclone  
sudo apt install swig liblgpio-dev python3-dev build-essential -y  
sudo apt-get install fonts-freefont-ttf  
curl -fsSL https://tailscale.com/install.sh | sh  
sudo tailscale up  

**\# Create a project folder**

mkdir reef\_monitor && cd reef\_monitor

\# Create and activate a Virtual Environment

python -m venv env

source env/bin/activate

**\# Install the necessary python libraries**

pip install gpiozero spidev luma.oled smbus2 rpi-lgpio

### Enable Hardware Interfaces

The design uses **SPI** (for the MCP3008s) and **I2C** (for the OLED). These are disabled by default.  
1.  In the SSH terminal, type: sudo raspi-config
2.  Navigate to **Interface Options**.
3.  Enable **I2C** and **SPI**.

### Transfer the code

Since we are on Windows, the easiest way to move your .py and config.txt files to the Pi is using **SCP** (Secure Copy). Open a _new_ PowerShell window on your Windows desktop (not the one logged into the Pi) and run:

PowerShell

\# Run this from the folder where your script is saved on Windows  
scp aquarium\_script.py config.txt pi@aquamon.local:~/reef\_monitor/

### Set the environment variables and activate environment

The code uses os.environ.get('AQUAMON\_EMAIL'), etc. We need to define these on the Pi so the script can see them.  
1.  In your SSH session, open the profile file: nano ~/.bashrc
2.  Scroll to the bottom and add:

export AQUAMON\_EMAIL=[your\_email@gmail.com](mailto:your_email@gmail.com)  
export AQUAMON\_EMAIL\_PW="your\_app\_password"  

source ~/reef\_monitor/env/bin/activate

1.  Save (**Ctrl+O, Enter**) and Exit (**Ctrl+X**).
2.  Refresh the variables: source ~/.bashrc

### Run and Automate

To test it:  
python reef\_monitor/aquarium\_script.py

Use a systemd service to have it start on boot and keep on running.

In the SSH session, run the following command to create a new service file:

Bash

sudo nano /etc/systemd/system/reef\_monitor.service

Service file:

[Unit]  
Description=Reef Aquarium Monitor Script  
After=network-online.target  
Wants=network-online.target  

[Service]  
User=aquamon  
\# Add Environment variable here  
Environment="AQUAMON_EMAIL=aquamonemail@gmail.com"  
Environment="AQUAMON_EMAIL_PW=abcdefghijklmnop"  
\# Path to your python interpreter and your script  
ExecStart=/home/aquamon/reef\_monitor/env/bin/python3 -u /home/aquamon/reef\_monitor/aquamon.py  
\# Working directory (helps if your script loads fonts or images from its own folder)  
WorkingDirectory=/home/aquamon/reef\_monitor  
\# Restart logic  
Restart=on-failure  
\# Wait 10 seconds before restarting to prevent rapid-fire loops  
RestartSec=10s  

[Install]  
WantedBy=multi-user.target  

Notice that I used Restart=on-failure. This is convenient for allowing on-going development and debug work. If the monitor exits with a 0 return code or if it is externally terminated by a signal, the service will not restart automatically. Only when the monitor ends abnormally will the service restart the monitor. During developement/debug I would typically stop the service and run the the monitor in an ssh'ed terminal session. I also have a reef shutdown service that runs separately to provide restart and shutdown via buttons. This would done as a separate service so that if the monitor ends or is hung, the restart and shutdown button actions would still be active.

sudo nano /etc/systemd/system/reef\_shutdown.service

[Unit]  
Description=Reef Monitor Hardware Shutdown Button  
After=network.target

[Service]  
Type=simple  
ExecStart=/usr/bin/python3 /home/aquamon/reef\_monitor/shutdown\_button.py  
Restart=always  
RestartSec=5  
User=root

[Install]  
WantedBy=multi-user.target  
### Managing the Monitor  

Now that it's running in the background, use these commands to check on it:

| Task | Command |
| --- | --- |
| Check if it's running | sudo systemctl status reef\_monitor.service |
| Stop the monitor | sudo systemctl stop reef\_monitor.service |
| Restart monitor | sudo systemctl restart reef\_monitor.service |
| View live logs | journalctl -u reef\_monitor.service -f |

### Install Rclone

**2\. Configure the OneDrive Remote**

The command rclone copy is **one-way only**. It behaves like a "push" or an "upload." It will take your local current.txt and upload it to the cloud. It will **not** look at what else is in your OneDrive and try to download it.

*   Run rclone config on Raspberry Pi.
*   Name it dropbox, pick the dropbox number.
*   When it asks **"Use auto config?"**, type **n** (No).
*   Copy the command given (e.g., rclone authorize "dropbox") and run it on your Windows PC.
*   Log in to Dropbox in your browser, click **Allow**, and paste the resulting token back into the Pi.

## Setup aliases

nano ~/.bash\_aliases

alias update-aquamon='rclone copyto dropbox:GitHub/Aquarium-Monitor/aquamon.py ~/reef\_monitor/aquamon.py && echo "aquam>  
alias update-config='rclone copyto dropbox:GitHub/Aquarium-Monitor/config.txt ~/reef\_monitor/config.txt && echo "config>  
alias monitor-logs='TZ="America/Chicago" journalctl -u reef\_monitor.service --no-pager -n 40'  

The update-\* aliases make code testing convenient. SSH to the system from your device, and assuming your device has dropbox access to the local repository directory, run the scripts to update the code and configuration files as needed.


## Monitor Enclosure

The enclosure and related parts were all printed on a 3D printer. I have included the FreeCad source files for these parts. They can be modified with FreeCad and/or exported to 3mf files for printing.

