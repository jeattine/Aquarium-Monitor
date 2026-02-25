
# Aquarium monitor

![Assembled3](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/assembled3.jpg)
Python-based aquarium monitor program running under the Raspberry Pi OS Lite Linux operating system on a Raspberry Pi 4 board. A Adafruit Perma-Proto Hat is mounted on the board to house two MCP3008 10-bit ADC with SPI interface. This provides the analog inputs to the monitor. The HAT also provides solder pads for each of the other GPIO pins used as digital inputs. The monitor has 24 RCA sockets for input of the sensors. It has a button to force a reset of the OS/monitor. The monitor provides two buttons for the calibration of the PH probe, with a PH-Low and a PH-High that can be set to the values of the calibration fluid in the configuration file. The calibration action will write its result back the configuration file. The monitor status, PH logs, and updated configuration files can be observed in a Dropbox folder by external devices. This is accomplished using 'rclone copyto'. Monitor alerts are surfaced by emails sent to the recipients listed in the configuration file. The monitor will autostart after the Linux OS boots. It is started via a service and set to be restarted if it abnormally terminates.

The program design has a 'Main' that constructs an GpioCtl object and loops calling methods on the GpioCtl object instantiation. 'Main' will stay in a continuous loop until an exception causes it to exit. The input to the program is a config.txt file expected to be in the current directory. This file is composed of two sections. The first section assigns the GPIO numbers of the hardware to various classes to read and process the sensor data connected to those GPIO inputs. Some examples are classes to monitor temperature, PH, Flow, water level, and light. These classes are derived from either a GPIO_Digital or a GPIO_Analog class, depending on the type of sensor. The GPIO_Digital and GPIO_Analog are derived from the GPIO base class. In addition to the GPIO assignment to classes, this section of the config file also gives a descriptive name to each GPIO input and defines the expected values/ranges/time-periods for operation.

Code structure:

![Class structure](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/Design2.png)   

![Class structure](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/ExampleOutput.png)


The Raspberry Pi board, Perma-Proto Hat with the two MCP3008 ICs, and the wiring to the RCA inputs:

![Internals](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/internal.jpg)

The custom 3D printed enclosure:

![Enclosure](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/enclosure.jpg)

The assembled unit:

![Assembled1](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/assembled1.jpg)

![Assembled2](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/assembled2.jpg)

The following images show the various sensors that feed the inputs to the GPIO device: 
  
  
![Flow Detection](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/FlowDetect.png)  
![Hi Low Level Detection](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/HiLowDetect.png)  
![Random Flow Detect](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/RandomFlowDetect.png)  
![Misc Detect](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/VariousDetect.png)  
![Conditional and Temp Detect](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/ConditionalTempDetect.png)  
![Battery Condition](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/BatteryCondition.png)
![PH Detect page 1](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/PhDetect.png)  

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

**1\. Create the Service File**

In the SSH session, run the following command to create a new service file:

Bash

sudo nano /etc/systemd/system/aquamon.service

Service file:

\[Unit\]

Description=Reef Aquarium Monitor Script

After=network.target

\[Service\]

User=aquamon

\# Add Environment variable here

Environment="AQUAMON\_EMAIL=[your\_email@gmail.com](mailto:your_email@gmail.com)"

Environment="AQUAMON\_EMAIL\_PW=\_PW=your\_app\_password"

\# Path to your python interpreter and your script

ExecStart=/home/aquamon/reef\_monitor/env/bin/python3 -u /home/aquamon/reef\_monitor/aquamon.py

\# Working directory (helps if your script loads fonts or images from its own folder)

WorkingDirectory=/home/aquamon/reef\_monitor

\# Restart logic

Restart=on-failure

\# Wait 10 seconds before restarting to prevent rapid-fire loops

RestartSec=10s

\[Install\]

WantedBy=multi-user.target

Also created a reef shutdown service that runs separately to provide restart and shutdown via buttons:

\[Unit\]

Description=Reef Monitor Hardware Shutdown Button

After=network.target

\[Service\]

Type=simple

ExecStart=/usr/bin/python3 /home/aquamon/reef\_monitor/shutdown\_button.py

Restart=always

RestartSec=5

User=root

\[Install\]

WantedBy=multi-user.target

### Managing the Monitor

Now that it's running in the background, use these commands to check on it:

| Task | Command |
| --- | --- |
| Check if it's running | sudo systemctl status aquamon.service |
| Stop the monitor | sudo systemctl stop aquamon.service |
| Restart monitor | sudo systemctl restart aquamon.service |
| View live logs | journalctl -u aquamon.service -f |

### Install Rclone

**2\. Configure the OneDrive Remote**

The command rclone copy is **one-way only**. It behaves like a "push" or an "upload." It will take your local current.txt and upload it to the cloud. It will **not** look at what else is in your OneDrive and try to download it.

*   Run rclone config on Raspberry Pi.
*   Name it dropbox, pick the dropbox number.
*   When it asks **"Use auto config?"**, type **n** (No).
*   Copy the command given (e.g., rclone authorize "dropbox") and run it on your Windows PC.
*   Log in to Dropbox in your browser, click **Allow**, and paste the resulting token back into the Pi.

## Monitor Enclosure

The enclosure and related parts were all printed on a 3D printer. I have included the FreeCad source files for these parts. They can be modified with FreeCad and/or exported to 3mf files for printing. 
  
