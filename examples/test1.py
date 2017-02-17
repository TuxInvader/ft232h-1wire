#!/usr/bin/python

# 1-wire over FT232H
#
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/126
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/187

import sys
sys.path.append("..")

from w1ftdi import W1ftdi
from ds18b20 import Ds18b20

debug = 2  # debug level 0 to 5
pin   = 8  # pin c0
overdrive = False

# Open and initialise the FT232h for 1-Wire
print "TEST 1: Perform Rom Search..."
w1 = W1ftdi(pin, debug, overdrive)
w1.open()
w1.sync()
w1.setup_clock()

# set some arbitrary GPIO states, and write them.
w1.set_pin(3, True, False)
w1.set_pin(7, True, False)
w1.write_gpio_state()

# Search for devices on the 1-Wire bus
if w1.reset():
    roms = w1.search_roms()
    print "Found roms: {}".format(roms)
w1.close()
print "TEST 1: Complete"

