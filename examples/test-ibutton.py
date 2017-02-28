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

debug = 2  # debug level 0 to 5
pullup = None
pin   = 8  # pin c0

print "TEST 1: Perform Rom Search in OverDrive..."
w1 = W1ftdi(pin, debug, pullup=pullup, overdrive=True)
w1.open()
w1.sync()
w1.setup_clock()

roms = None
if w1.reset():
    w1.skip_rom_od()
    roms = w1.search_roms()
    print "Found roms: {}".format(roms)
w1.close()
print "TEST 1: Complete"

if roms is None:
    raise Exception("No ROMS")

print "TEST 2: Read Version, change passwords"
for rom in roms:
    if rom[0:2] == "37":
        print "ROM {} is a DS1977, reading Version".format(rom)
        ds = Ds1977(pin, debug, rom, pullup=pullup)
        print "Version: {:d}".format( ds.get_version() )
        ds.change_passwords("QWERTYUI","qwertyui","qwertyui")
        #ds.enable_passwords(False, "qwertyui")
        ds.close()
    else:
        print "ROM {} is NOT a DS1977, Skipping.".format(rom)
print "TEST 2: Complete"

print "TEST 3: Write a page"
for rom in roms:
    if rom[0:2] == "37":
        print "ROM {} is a DS1977".format(rom)
        ds = Ds1977(pin, debug, rom)
        data = 'DEADBEEF' * 8
        print "Writing data to SP: {}".format(data)
        if ds.write_scratchpad(0x00,0x00,data):
            print "Page written and verified"
        data = ds.read_scratchpad(64)
        print "Reading back SP: {}".format(data[3])
        print "Copying data to EEPROM"
        ds.copy_scratchpad(0x00, 0x00, 63, "password" )
        ds.close()
    else:
        print "ROM {} is NOT a DS1977, Skipping.".format(rom)
print "TEST 3: Complete"

print "TEST 4: Read a page"
for rom in roms:
    if rom[0:2] == "37":
        print "ROM {} is a DS1977".format(rom)
        ds = Ds1977(pin, debug, rom)
        pages = ds.read_memory(0x00, 0x00, "password", 1)
        print "Read a single page: {}".format(pages[0])
        pages = ds.read_memory(0x1f, 0x00, "password", 1)
        print "Read half a page: {}".format(pages[0])
        pages = ds.read_memory(0x00, 0x00, "password", 2)
        print "Read two pages 1/2: {}".format(pages[0])
        print "Read two pages 2/2: {}".format(pages[1])
        pages = ds.read_pages(506, "password", 0)
        for page in pages:
            print "Page: {}".format(page)
        ds.close()
print "TEST 4: Complete"


