# Aquarium-Monitor
Python-based aquarium monitor program to interface with the Numato ethernet 16 channel GPIO module. Can be adapted to other GPIO devices. The following is a system view of the aquarium monitor.  
![System view](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/SystemView.png)   
The monitor program requires Python3 but no higher than Python 3.11. It uses the telnet class that has been deprecated in Python 3.11 and removed in 3.13. There are no immediate plans to support running in 3.13+. The program design has a 'Main' that constructs an GpioCtl object and loops calling methods on the GpioCtl object instantiation. 'Main' will stay in a continuous loop until an exception causes it to exit. A keyboard exception would be the only expected exiting condition. The input to the program is a config.txt file expected to be in the current directory. This file is composed of two sections. The first section assigns the GPIO numbers of the hardware to various classes to read and process the sensor date connected to those GPIO inputs. Some examples are classes to monitor temperature, PH, Flow, water level, and light. These classes are derived from either a GPIO_Digital or a GPIO_Analog class, depending on the type of sensor. The GPIO_Digital and GPIO_Analog are derived from the GPIO base class. In addition to the GPIO assignment to classes, this section of the config file also gives a descriptive name to each GPIO input and defines the expected values/ranges/time-periods for operation.  
![Class structure](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/Design.png)   
The second section of the configuration file contains network and sampling configuration data. This includes login information, IP address of the device, sample times, email addresses, smp server info, and various other data. There are two distinct outputs from the monitor: email alerts and a status file. Every number of seconds defined in the config file, the status file is written out to a cloud drive. I am personally using OneDrive, but any cloud drive would work. I have access to my cloud drive from all of my mobile devices, allowing me to check the status whenever I want. The other output is an email alert. These are sent when a sensor does not meet the conditions specified in the config file. The email can be configured to be sent to one or multiple addresses. The following screenshots show and example of an alert email and a status file:  
![Class structure](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/ExampleOutput.png)  
The monitor is resilient to network or device clitches. If communication to the GPIO device is interrupted, it will repeatedly attempt to re-establish the connection. The following screenshot shows a successful reconnection. In this case, the GPIO unit was powered down temporarily for aquarium maintenance.  
![Resilience](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/Resilience.png)  
I currently have the monitor running on a Windows 11 system; however, in the past I have sucessfully run on a Linux system. The program can run on Linux without modification. The reason I have it running on Windows 11 is that I already have a home Windows 11 computer for other reasons and I did not want to require a separate computer for the monitor. A problem with running on Windows 11 is that control of automatic reboots is limited. For example, I don't want the computer rebooting while I am away on vacation. I found a YouTube video provided by PPR Computers that can postpone the reboots indefinitely. I configure the Windows task manager to run the follow script every hour. The script bumps up the 'active' window so that Windows thinks that the reboot can be done at a future time that it never reaches.  
![Disable Reboot](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/DisableBoot.png)  
  
The following images show the various sensors that feed the inputs to the GPIO device: 
  
  
![Flow Detection](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/FlowDetect.png)  
![Hi Low Level Detection](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/HiLowDetect.png)  
![Random Flow Detect](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/RandomFlowDetect.png)  
![Misc Detect](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/VariousDetect.png)  
![Conditional and Temp Detect](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/ConditionalTempDetect.png)  
![PH Detect page 1](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/PhDetect.png)  
![PH Detect page 2](https://github.com/jeattine/Aquarium-Monitor/blob/main/images/Ph2Detect.png)  


  
