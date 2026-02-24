#!/usr/bin/env python3
from gpiozero import Button
from subprocess import check_call
from signal import pause
import time

# Bounce_time filters out the electrical noise
btn = Button(6, hold_time=5, pull_up=True, bounce_time=0.05)
last_release_time = 0
double_click_threshold = 0.5
was_held = False

def handle_hold():
    global was_held
    was_held = True
    print("Long-press detected: Shutting down now...")
    check_call(['sudo', 'poweroff'])

def handle_release():
    global was_held
    global last_release_time
    # If the button was held for 'hold_time' seconds, handle_hold already fired.
    # We do nothing on release.
    if was_held:
        was_held = False # Reset for next time
        return
    current_time = time.time()
    # If the time since last click is between 0.05s and 0.5s, it's a double-click
    if 0.05 < (current_time - last_release_time) < double_click_threshold:
        print("Confirmed Double-click: Rebooting...")
        check_call(['sudo', 'reboot'])
    last_release_time = current_time

# Assign the events
btn.when_held = handle_hold
btn.when_released = handle_release

pause()
