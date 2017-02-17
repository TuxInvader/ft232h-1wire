#!/usr/bin/python
#
# Test using the Adafruit GPIO Library modified to support 1-wire, see:
# https://github.com/TuxInvader/Adafruit_Python_GPIO
#
# Same as test1, but using Adafruit_GPIO library

import time
import struct
 
# Import GPIO, FT232H, and LED modules.
import Adafruit_GPIO as GPIO
import Adafruit_GPIO.FT232H as FT232H

# Pin Assignments for the various GPIO
one_wire_pin=8    # C0 Pin

# Temporarily disable the built-in FTDI serial driver on Mac & Linux platforms.
FT232H.use_FT232H()
 
# Create an FT232H object that grabs the first available FT232H device found.
ft232h = FT232H.FT232H()
 
# Open and initialise the FT232h for 1-Wire
print "TEST 1: Perform Rom Search..."
owm = FT232H.OneWireMaster(ft232h, one_wire_pin)

# set some arbitrary GPIO states, and write them.
owm.set_pin(3, True, False)
owm.set_pin(7, True, False)

# Search for devices on the 1-Wire bus
if owm.reset():
    roms = owm.search_roms()
    print "Found roms: {}".format(roms)
print "TEST 1: Complete"

