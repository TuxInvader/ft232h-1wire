#!/usr/bin/python

# 1-wire over FT232H
#
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/126
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/187

import sys
sys.path.append("..")

from w1ftdi import W1ftdi
from ds1977 import Ds1977
import time

debug = 3  # debug level 0 to 5
pin   = 8  # pin c0

print "TEST 1: Perform Rom Search..."
#w1 = W1ftdi(pin, debug)
#w1.open()
#w1.sync()
#w1.setup_clock()

roms = None
roms = ["37:8a:b8:1b:00:00:00:5f"]
#if w1.reset():
#    roms = w1.search_roms()
#    print "Found roms: {}".format(roms)
#w1.close()
#print "TEST 1: Complete"

if roms is None:
    raise Exception("No ROMS")

print "TEST 2: Read Version"
for rom in roms:
    if rom[0:2] == "37":
        print "ROM {} is a DS1977, reading Version".format(rom)
        ds = Ds1977(pin, debug, rom)
        if ds.reset():
            print "Version: {:d}".format( ds.get_version() )
            ds.change_passwords("QWERTYUI","qwertyui","qwertyui")
            #ds.enable_passwords(False, "qwertyui")
        ds.close()
    else:
        print "ROM {} is NOT a DS1977, Skipping.".format(rom)
print "TEST 2: Complete"
