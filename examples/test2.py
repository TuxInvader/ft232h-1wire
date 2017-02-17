#!/usr/bin/python

# 1-wire over FT232H
#
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/126
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/187

import sys
sys.path.append("..")

from w1ftdi import W1ftdi
from ds18b20 import Ds18b20

debug = 1  # debug level 0 to 5
pin   = 8  # pin c0

print "TEST 1: Perform Rom Search..."
w1 = W1ftdi(pin, debug)
w1.open()
w1.sync()
w1.setup_clock()

if w1.reset():
    roms = w1.search_roms()
    print "Found roms: {}".format(roms)
w1.close()
print "TEST 1: Complete"

print "TEST 2: Read Temperature"
for rom in roms:
    if rom[0:2] == "28":
        print "ROM {} is a DS18B20, reading Temperature".format(rom)
        ds = Ds18b20(pin, debug, rom)
        celsius = ds.get_temp()
        print "Temp {} C".format(celsius)
        ds.close()
    else:
        print "ROM {} is NOT a DS18B20, Skipping.".format(rom)
print "TEST 2: Complete"
