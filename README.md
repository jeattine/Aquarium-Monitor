
# Aquarium monitor
Python-based aquarium monitor program running under the Raspberry Pi OS Lite Linux operating system on a Raspberry Pi 4 board. A Adafruit Perma-Proto Hat is mounted on the board to house two MCP3008 10-bit ADC with SPI interface. This provides the analog inputs to the monitor. The HAT also provides solder pads for each of the other GPIO pins used as digital inputs. The monitor has 24 RCA sockets for input of the sensors. It has a button to force a reset of the OS/monitor. The monitor provides two buttons for the calibration of the PH probe, with a PH-Low and a PH-High that can be set to the values of the calibration fluid in the configuration file. The calibration action will write its result back the configuration file. The monitor status can be observed in a Microsoft OneDrive file by external devices. This is accomplished by setting up an Rclone mount. The mount also provides the version of the config file and python program that the monitor will run. Monitor alerts are emails set to the recipients listed in an evironment variable. The monitor will autostart after the Linux OS boots. It is started via a service and set to be restarted if it abnormally terminates.

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


  
