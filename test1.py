#!/usr/bin/python

# 1-wire over FT232H
#
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/126
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/187

from w1ftdi import W1ftdi
from ds18b20 import Ds18b20

debug = 5  # debug level 0 to 5
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

