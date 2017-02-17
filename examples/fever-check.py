#!/usr/bin/python
#
# Test using the Adafruit GPIO Library modified to support 1-wire, see:
# https://github.com/TuxInvader/Adafruit_Python_GPIO
#

import time
import struct
 
# Import GPIO, FT232H, and LED modules.
import Adafruit_GPIO as GPIO
import Adafruit_GPIO.FT232H as FT232H
from Adafruit_LED_Backpack import SevenSegment

# If you have more than one DS18B20 sesnor connected, then you must
# provide it's ROM code here
ds_rom=None

# Pin Assignments for the various GPIO
one_wire_pin=8    # C0 Pin
white_pin=7       # D7 Pin
red_pin=6         # D6 Pin
green_pin=5       # D5 Pin

# Target temperature 37.0 +/- 0.8 C
# DS18B20 are accurate to +/- 0.5 C
temp_target = 37.0
temp_range = 0.8 + 0.5

# Number of values which must consistently match to consider measurment complete
temp_settled = 5

# Raw LED Patterns
ALPHA_VALUES = { "A": 0x77, "E": 0x79, "D": 0x5e, "R": 0x50 }

# Temporarily disable the built-in FTDI serial driver on Mac & Linux platforms.
FT232H.use_FT232H()
 
# Create an FT232H object that grabs the first available FT232H device found.
ft232h = FT232H.FT232H()
 
# Initialise the LED Display
led = SevenSegment.SevenSegment(i2c=ft232h)
led.begin()

# Initialise the 1-wire bus
owm = FT232H.OneWireMaster(ft232h, one_wire_pin)

# FLASH the LEDS at startup
owm.set_pin(white_pin, GPIO.OUT, GPIO.LOW)
owm.set_pin(red_pin, GPIO.OUT, GPIO.LOW)
owm.set_pin(green_pin, GPIO.OUT, GPIO.LOW)

owm.set_pin(white_pin, GPIO.OUT, GPIO.HIGH)
time.sleep(0.5)
owm.set_pin(white_pin, GPIO.OUT, GPIO.LOW)

owm.set_pin(red_pin, GPIO.OUT, GPIO.HIGH)
time.sleep(0.5)
owm.set_pin(red_pin, GPIO.OUT, GPIO.LOW)

owm.set_pin(green_pin, GPIO.OUT, GPIO.HIGH)
time.sleep(0.5)
owm.set_pin(green_pin, GPIO.OUT, GPIO.LOW)

# Print rEAD to the LED
led.clear()
led.set_digit_raw(0, ALPHA_VALUES["R"])
led.set_digit_raw(1, ALPHA_VALUES["E"])
led.set_digit_raw(2, ALPHA_VALUES["A"])
led.set_digit_raw(3, ALPHA_VALUES["D"])
led.write_display()

settled = [ i for i in xrange(temp_settled) ]
counter = 0
while len(set(settled)) != 1:

    # Turn on white_pin
    owm.set_pin(white_pin, GPIO.OUT, GPIO.HIGH)

    # Address the sensor, and ask it to read the temperature
    owm.reset()
    owm.address_rom(ds_rom)
    owm.write_byte(0x44)
    time.sleep(1)

    # Read the data from the Sensor
    owm.reset()
    owm.address_rom(ds_rom)
    owm.write_byte(0xbe)
    data = owm.read_bytes(9)

    # Check the CRC on the data:
    if owm.crc(data) is not 0x00:
        raise Exception("CRC Check Failed")

    # Calculate the temp based on the current resolution
    resolution = ( data[4] >> 5) & 0b11
    temp_register = struct.unpack('<h', data[0:2])[0]
    if resolution == 3:
        temperature = float(temp_register) / 16.0
    elif resolution == 2:
        temperature = float(temp_register >> 1) / 8.0 
    elif resolution == 1:
        temperature = float(temp_register >> 2) / 4.0 
    elif resolution == 0:
        temperature = float(temp_register >> 3) / 2.0 
    else:
        raise Exception("Unknown Resolution")

    print "Temperature: {:.2f}C".format(temperature)
    led.clear()
    led.print_float(temperature, decimal_digits=2)
    led.write_display()

    # Update the settled list
    settled[counter%temp_settled] = temperature
    counter += 1

    # Turn off white_pin
    owm.set_pin(white_pin, GPIO.OUT, GPIO.LOW)
    time.sleep(1)

if settled[0] > (temp_target-temp_range) and settled[0] < (temp_target+temp_range):
    owm.set_pin(green_pin, GPIO.OUT, GPIO.HIGH)
    print "The child seems fine"
else:
    owm.set_pin(red_pin, GPIO.OUT, GPIO.HIGH)
    print "Call the doctor!"

