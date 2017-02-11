#!/usr/bin/python

# 1-wire over FT232H
# DS18B20 Temp Sensor 
#
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/126
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/187

from w1ftdi import W1ftdi
import time
import struct

class Ds18b20(W1ftdi):

    # init
    def __init__(self, pin, debug=0, rom=None):
        self.rom = rom
        super(Ds18b20, self).__init__(pin, debug)
        self.open()
        self.sync()
        self.setup_clock()
        
    # Read Temperature 
    def get_temp(self):

        # Reset the line, bail if no devices
        if self.reset() is False:
            raise Exception("No Device")

        # Ask Sesnsor to take a measurement
        self.address_rom(self.rom)
        self.write_byte(0x44)
        self.flush_write_buffer()
        self.debug(1, "TEMP: Waiting for measurement")
        time.sleep(1)

        # Read the data from the Sensor
        self.reset()
        self.address_rom(self.rom)
        self.write_byte(0xbe)
        data = self.read_bytes(9)

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
        self.debug(1, "Resolution: {}".format(resolution))
        self.debug(1, "Data: {}".format( self.bytes2string(data)))
        return temperature
        
