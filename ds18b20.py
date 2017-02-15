#!/usr/bin/python

# 1-wire over FT232H
# DS18B20 Temp Sensor 
#
# 1-wire specs
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/126
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/187
#
# Temp Spec
# http://datasheets.maximintegrated.com/en/ds/DS18B20.pdf
#
# command_buffer management is disabled, because per byte buffering in parent
# seems to be faster, than buffering long command strings.

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
        self.res = { 3: "12 bit", 2: "11 bit", 1: "10 bit", 0: "9 bit" }
        
    # Read Temperature 
    def get_temp(self):

        # Reset the line, bail if no devices
        if self.reset() is False:
            raise Exception("No Device")

        # Ask Sesnsor to take a measurement
        #self.enable_command_buffer()
        self.address_rom(self.rom)
        self.write_byte(0x44)
        #self.flush_command_buffer()
        self._debug(1, "TEMP: Waiting for measurement")
        time.sleep(1)

        # Read the data from the Sensor
        self.reset()
        #self.enable_command_buffer()
        self.address_rom(self.rom)
        self.write_byte(0xbe)
        #self.flush_command_buffer()
        data = self.read_bytes(9)

        # Check the CRC on the data:
        if self.crc(data) is not 0x00:
            self._debug(1, "TEMP: CRC Check Failed")
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
        self._debug(1, "TEMP: Resolution: {}".format(self.res[resolution]))
        self._debug(1, "TEMP: Data: {}".format( self.bytes2string(data)))
        return temperature
        
