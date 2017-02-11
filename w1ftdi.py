#!/usr/bin/python

# 1-wire over FT232H
#
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/126
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/187

import atexit
import subprocess
import os
import time
import ftdi1 as ftdi
import math
import struct
import codecs

FT232H_VID = 0x0403   # Default FTDI FT232H vendor ID
FT232H_PID = 0x6014   # Default FTDI FT232H product ID
DEBUG = 0             # level 0 to 5

class W1ftdi(object):

    def __init__(self, pin, debug=DEBUG):
        self.rmmod()
        self._debug = debug
        self._ctx = ftdi.new()
        self._level = 0x0000
        self._direction = 0x0000
        self._buffer = False
        self._output = None
        self._pin = pin

        # Figure out the clock speeds needed for the delays
        self.clock_A = self._get_delay(0.000006)
        self.clock_B = self._get_delay(0.000064)
        self.clock_C = self._get_delay(0.000060)
        self.clock_D = self._get_delay(0.000010)
        self.clock_E = self._get_delay(0.000009)
        self.clock_F = self._get_delay(0.000055)
        self.clock_G = self._get_delay(0.000000)
        self.clock_H = self._get_delay(0.000480)
        self.clock_I = self._get_delay(0.000070)
        self.clock_J = self._get_delay(0.000410)

        # Two ways to delay. dump a byte to tms, or pulse the clock for n
        # bits. A 1 bit pulse seems to take the same as time as a 8bit 
        # dump to TMS? Default is to pulse the clock.
        self.tms_dump    = '\x4a\x01\xff'  # Dump 8 bits to TMS
        self.pb          = '\x8e\x01'      # Pulse clock (1 bits) 
        self.delay       = self.pb

        # MPSSE Command to read GPIO
        self.read_gpio   = '\x81\x83'
        
        self.set_pin(True, False)
        self.low = self.get_gpio()

        self.set_pin(False, True)
        self.high = self.get_gpio()

        if self._ctx == 0:
            raise Exception("Failed to open FTDI")
        atexit.register(self.close)

    # Debug function
    def debug(self, level, msg):
        if self._debug >= level:
            print "DEBUG {} {:.9f}, {}".format(level, time.time(), msg)

    # Remove the kernels FTDI Serial modules
    def rmmod(self):
        subprocess.call('modprobe -r -q ftdi_sio', shell=True)
        subprocess.call('modprobe -r -q usbserial', shell=True)

    # Return the MPSSE command required to set the clock to a given frequency
    def _set_clock(self, clock_hz):
        divisor = int(math.ceil((30000000.0-float(clock_hz))/float(clock_hz))) & 0xFFFF
        valueH = ( divisor >> 8 ) & 0xFF
        valueL = divisor & 0xFF
        return bytearray((0x86, valueL, valueH))

    # Figure out the frequency required for a specific delay
    def _get_delay(self, seconds):
        if seconds == 0:
            freq = 30000000.0
        else:
            freq = ( 1.00 / seconds ) * 2
        self.debug(3, "Delay: {:0.6f}, Freq: {}".format(seconds, freq))
        return self._set_clock(freq)

    # Buffer write commands and then send them to the MPSSE with a flush
    def enable_write_buffer(self):
        if self._buffer:
            raise Exception("Buffering was already enabled!!")
        self._buffer = True
        self._output = None

    # flush buffered commands to the MPSSE
    def flush_write_buffer(self):
        self._buffer = False
        if self._output is not None:
            self._write(self._output)
            self._output = None
        
    # Write data to the FTDI MPSSE engine
    def _write(self, string):
        length = len(string)
        if self._buffer:
            if self._output is None:
                self._output = string
            else:
                self._output += string
            self.debug(5, "Buffering: " + "".join("{:02x}".format(ord(c)) for c in self._output))
            return
        self.debug(5, "Write: " + "".join("{:02x}".format(ord(c)) for c in string))
        ftdi.write_data(self._ctx, string, length)

    # Read data from the FTDI MPSSE engine
    def _read(self, length, timeout=5):
        start = time.time()
        response = bytearray(length)
        count = 0
        while count < length:
            if ( time.time() - start >= timeout ):
                raise Exception("FTDI Read Timeout")
            read, data = ftdi.read_data(self._ctx, length - count)
            if read < 0:
                raise Exception("USB Error: {}".format(read))
            response[count:read] = data[:read]
            count += read
            time.sleep(0.01)
        self.debug(5, "Read: " + "".join("{:02x}".format(c) for c in response))
        return response

    # Flush bytes in the MPSSE read buffer
    def flush(self):
        self.debug(4, "MPSSE: Flushing")
        try:
            while True:
                self._read(1,1)
        except:
            self.debug(4, "MPSSE: Flushed")
            pass

    # Open the FTDI and prepare the MPSSE engine for use.
    def open(self):
        self.debug(3, "MPSSE: Open")
        ftdi.usb_open(self._ctx, FT232H_VID, FT232H_PID)
        ftdi.usb_reset(self._ctx)
        ftdi.read_data_set_chunksize(self._ctx, 65535)
        ftdi.write_data_set_chunksize(self._ctx, 65535)
        # RESET MPSSE
        ftdi.set_bitmode(self._ctx, 0, 0)
        # Enable MPSSE
        ftdi.set_bitmode(self._ctx, 0, 2)

    # Cleanup the FTDI connection and release it.
    def close(self):
        if self._ctx is not None:
            self.debug(3, "MPSSE: Closed. FTDI Released")
            ftdi.free(self._ctx)
        self._ctx = None

    # Synchronize the MPSSE engine by sending the bad command and look through the
    # buffe until we see it's rejection.
    def sync(self):
        self.debug(3, "MPSSE: Sync")
        retries = 10
        tries = 0
        self._write('\xAB')
        sync = False
        while not sync:
            data = self._read(2)
            if data == '\xFA\xAB':
                sync = True
            tries += 1
            if tries >= retries:
                raise Exception("Failed to sync with MPSSE")

    # Set up the clock to be consistent, and to use the full 60Mhz
    def setup_clock(self):
        self.debug(3, "MPSSE: Setup Clock")
        commands = bytearray((
            0x8a,   # turn off clock divide by 5.
            0x97,   # turn off adaptive clocking
            0x8d))  # turn off 3-phase clocking
        self._write(str(commands))

    # Get the bytes representing the current GPIO state, and return the
    # MPSSE Command needed to set them to this state
    def get_gpio(self):
        commands = bytearray((
            0x80,                                # write low bytes
            chr(self._level & 0xFF),             # Low Level
            chr(self._direction & 0xFF),         # Low Direction
            0x82,                                # Read high bytes
            chr((self._level >> 8) & 0xFF),      # High Level
            chr((self._direction >> 8) & 0xFF))) # High Direction
        return commands

    # Write the GPIO to the MPSSE
    def write_gpio(self):
        self.debug(3, "GPIO: Writing GPIO")
        self._write(str(self.get_gpio()))

    # Set the GPIO pin to in/out and high/low
    def set_pin(self, out, high):
        self.debug(3, "GPIO: Setting Pin: {}, Out: {}, High: {}".format(self._pin, out, high))
        if out:
            self._direction |= (1 << self._pin) & 0xFFFF
        else:
            self._direction &= ~(1 << self._pin) & 0xFFFF
        if high:
            self._level     |= ~(1 << self._pin) & 0xFFFF
        else:
            self._level     &= ~(1 << self._pin) & 0xFFFF

    # Here begins the 1-wire stuff

    # Send a 1-wire reset on the GPIO, This makes all slaves listen up for commands.
    # It also detects the presance of the slaves. If nothing responds, then no devices
    # are connected and we return false.
    def reset(self):

        self.debug(2, "1Wire: Reset")
        #self.flush()
        commands = self.clock_H + self.low + self.delay + self.high + self.clock_I + self.delay + \
                    self.read_gpio + self.clock_J + self.delay + self.read_gpio 

        self._write(str(commands))
        present = self._read(4)

        if present == '\xff'*4:
            self.debug(2, "1Wire: No Devices Present")
            return False
        else:
            self.debug(2, "1Wire: Devices Present")
            return True

    # Write a bit to the 1-wire bus, either a 1 or a 0
    def write_bit(self, bit):
        self.debug(5, "1Wire: Write Bit: {}".format(bit))
        if bit:
            commands = self.clock_A + self.low + self.delay + self.high + self.clock_B + self.delay 
        else:
            commands = self.clock_C + self.low + self.delay + self.high + self.clock_D + self.delay

        self._write(str(commands))

    # Read a bit from the 1-wire bus.
    def read_bit(self):
        commands = self.clock_A + self.low + self.delay + self.high + self.clock_E +\
                    self.delay + self.read_gpio + self.clock_F + self.delay

        self._write(str(commands))
        bit = self._read(2)
        state = struct.unpack("H", bit)[0] >> self._pin & 01
        self.debug(5, "1Wire: Read Bit: {:02x}{:02x} - Pin: {} is {}".format(bit[0],bit[1], self._pin, state))
        return state
            
    # Use the write_bit function to write bytes out to the bus
    def write_byte(self, byte):
        self.debug(4, "1Wire: Write Byte: {:02x}".format(byte))
        for i in range(8):
            self.write_bit(byte & 1)
            byte >>= 1

    # write multiple bytes to the bus
    def write_bytes(self, data):
        for byte in data:
            self.write_byte(byte)

    # Use the read_bit function to read bytes from the bus
    def read_byte(self):
        byte = 0
        for i in range(8):
            bit = self.read_bit()
            byte |= bit << i
        self.debug(4, "1Wire: Read Byte: {:02x}".format(byte))
        return byte 

    # Read multiple bytes from the 1-wire bus
    def read_bytes(self, count):
        data = bytearray(count)
        for i in range(count):
            data[i] = self.read_byte()
        return data

    # read multiple bits from the 1-wire bus. Used for device discovery
    def read_bits(self, count):
        bits = []
        for i in range(count):
            bits.append( self.read_bit() )
        return bits
    
    # There is only one device on the bus, so ask it to identify itself.
    def rom_read(self):
        rom = bytearray(8)
        self.write_byte(0x33)
        for i in range(8):
            rom[i] = self.read_byte()
        self.debug(1, "rom_read discovered: {}".format(self.bytes2string(rom)))
        return rom 

    # There is only one device on the bus so skip ROM matching.
    def skip_rom(self):
        self.write_byte(0xcc)

    # Search for ROMs on the 1-wire bus
    def search_roms(self):
        roms_found = []
        partials = [ [] ]
        self.debug(1, "Search Start")
        while len(partials) > 0:
            self.debug(1, "Searching....")
            rom = partials.pop()
            roms_found.append( self.bytes2string(self._search(rom, partials)) )
        self.debug(1, "Search Complete")
        return roms_found
        
    # Do the search for each partial ROM
    def _search(self, rom=[], partials=[]):

        if self.reset() is False:
            return

        self.write_byte(0xf0)

        for bit in rom:
            bits = self.read_bits(2)
            if bits is [True, True]:
                if len(rom) == 0:
                    self.debug(1, "No Devices")
                    return
                else:
                    raise Exception("feck")
            self.write_bit(bit)

        for i in range(64 - len(rom)):
            bits = self.read_bits(2)
            if bits[0] != bits[1]:
                self.debug(2, "Search Match: Found single host or matching bits. Continuing")
                rom.append(bits[0])
                self.write_bit(bits[0])
            elif bits == [False, False]:
                self.debug(1, "Search Fork: Found mismatch. Storing partial. Continuing")
                np = list(rom)
                np.append(True)
                partials.append( np )
                rom.append(False)
                self.write_bit(False)
            else:
                self.debug(1, "Search Fail: Unexpected end of Device Search. No Response from slaves")
                raise Exception("Search Failed. Device Comms Interrupted")

        complete = bytearray(8)
        for i in range(8):
            byte = 0
            for o in range(8):
                bit = rom[(i*8)+o]
                byte |= bit << o
            complete[i] = byte

        self.debug( 1, "Search Found: ROM {}".format( self.bytes2string(complete)))
        return complete
        
        
    # Target the ROM specified
    def _match_rom(self, rom):
        if type(rom) is str:
            rom = self.string2bytes(rom)
        self.write_byte(0x55)
        self.write_bytes(rom)

    # Address the ROM if given, else perform a skip_rom()
    def address_rom(self, rom):
        if rom is None:
            self.skip_rom()
        else:
            self._match_rom(rom)
        
    # Return an a string representation of the device ROM
    def bytes2string(self, bytesarray):
        return ":".join("{:02x}".format(c) for c in bytesarray)

    # Convert a hexadecimal string to bytes
    def string2bytes(self, string):
        return bytearray(codecs.decode(string.replace(":",""),"hex"))

