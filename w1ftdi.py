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
OVERDRIVE = False     # Should Overdrive be used?

class W1ftdi(object):

    def __init__(self, pin, debug=DEBUG, overdrive=OVERDRIVE, pullup=None):
        self._rmmod()
        self._dbg = debug
        self._ctx = ftdi.new()
        self._level = 0x0000
        self._direction = 0x0000
        self._buffer = False
        self._output = None
        self._debug(1, "1Wire: Init")
        self._max_buffer = 0
        self._overdrive = overdrive
        self._od = False
        self._rc = False
        self._gpiol1 = 5

        # Set the pin to use
        self.pin = pin
        self.pullup = pullup

        # Set up delay timers (clock frequencies)
        self._reset_clocks(False)

        # Two ways to delay. dump a byte to tms, or pulse the clock for n
        # bits. A 1 bit pulse seems to take the same as time as a 8bit 
        # dump to TMS? Default is to pulse the clock.
        self.tms_dump    = '\x4a\x01\xff'  # Dump 8 bits to TMS
        self.pb          = '\x8e\x01'      # Pulse clock (1 bits) 
        self.delay       = self.pb

        # MPSSE Command to read GPIO
        self.read_gpio   = '\x81\x83'

        # If we have a pullup pin, set it to low by default, this pin controls
        # switching on a strong_pullup if the device needs extra power. It is
        # activated when pullup_and_check() is called.
        # set_pin() always sets our GPIO flags for our GPIO pin too, so that gets
        # done here regardless of having an addition pullup control pin.
        if self.pullup is not None:
            self.set_pin(self.pullup, False, False)
        else:
            self.set_pin(self.pin, False, True)
        self.write_gpio_state()

        # Create the context for FTDI
        if self._ctx == 0:
            raise Exception("Failed to open FTDI")
        atexit.register(self.close)

    # Debug function
    def _debug(self, level, msg):
        if self._dbg >= level:
            print "DEBUG {} {:.9f}, {}".format(level, time.time(), msg)

    # Remove the kernels FTDI Serial modules
    def _rmmod(self):
        subprocess.call('modprobe -r -q ftdi_sio', shell=True)
        subprocess.call('modprobe -r -q usbserial', shell=True)

    # Return the MPSSE command required to set the clock to a given frequency
    # for the provided delay
    def _get_delay_cmd(self, seconds):
        if seconds == 0:
            clock_hz = 30000000.0
        else:
            clock_hz = ( 1.00 / seconds ) * 2
        self._debug(3, "Delay: {:0.7f}, Freq: {}".format(seconds, clock_hz))

        divisor = int(math.ceil((30000000.0-float(clock_hz))/float(clock_hz))) & 0xFFFF
        valueH = ( divisor >> 8 ) & 0xFF
        valueL = divisor & 0xFF
        return bytearray((0x86, valueL, valueH))

    # Set up the delay timings, needs to be run at initialisation, and when
    # switching to/from overdrive mode
    def _reset_clocks(self, overdrive):

        if self._overdrive and overdrive:
            self._debug(2, "1Wire: Overdrive is enabled")
            # overdrive speeds
            self._od = True
            self.clock_A = self._get_delay_cmd(0.0000010)
            self.clock_B = self._get_delay_cmd(0.0000075)
            self.clock_C = self._get_delay_cmd(0.0000075)
            self.clock_D = self._get_delay_cmd(0.0000025)
            self.clock_E = self._get_delay_cmd(0.0000010)
            self.clock_F = self._get_delay_cmd(0.0000070)
            self.clock_G = self._get_delay_cmd(0.0000050)
            self.clock_H = self._get_delay_cmd(0.0000480)
            self.clock_I = self._get_delay_cmd(0.0000075)
            self.clock_J = self._get_delay_cmd(0.0000400)
            self.clock_Z = self._get_delay_cmd(0.000000)
        else:
            # standard clock speeds
            self._debug(2, "1Wire: Overdrive is disabled")
            self._od = False
            self.clock_A = self._get_delay_cmd(0.000006)
            self.clock_B = self._get_delay_cmd(0.000064)
            self.clock_C = self._get_delay_cmd(0.000060)
            self.clock_D = self._get_delay_cmd(0.000010)
            self.clock_E = self._get_delay_cmd(0.000009)
            self.clock_F = self._get_delay_cmd(0.000055)
            self.clock_G = self._get_delay_cmd(0.000000)
            self.clock_H = self._get_delay_cmd(0.000480)
            self.clock_I = self._get_delay_cmd(0.000070)
            self.clock_J = self._get_delay_cmd(0.000410)
            self.clock_Z = self._get_delay_cmd(0.000000)

    # Buffer write commands and then send them to the MPSSE with a flush
    def enable_command_buffer(self):
        if self._buffer:
            raise Exception("Buffering was already enabled!!")
        self._buffer = True
        self._output = None

    # flush buffered commands to the MPSSE
    def flush_command_buffer(self):
        self._buffer = False
        if self._output is not None:
            if len(self._output) > self._max_buffer:
                self._max_buffer = len(self._output)
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
            self._debug(5, "MPSSE: Buffering: " + "".join("{:02x}".format(ord(c)) for c in self._output))
            return
        self._debug(5, "MPSSE: Write: " + "".join("{:02x}".format(ord(c)) for c in string))
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
        self._debug(5, "MPSSE: Read: " + "".join("{:02x}".format(c) for c in response))
        return response

    # Flush bytes in the MPSSE read buffer
    def flush(self):
        self._debug(4, "MPSSE: Flushing")
        try:
            while True:
                self._read(1,1)
        except:
            self._debug(4, "MPSSE: Flushed")
            pass

    # Open the FTDI and prepare the MPSSE engine for use.
    def open(self, usb_reset=True):
        self._debug(3, "MPSSE: Open")
        ftdi.usb_open(self._ctx, FT232H_VID, FT232H_PID)
        if usb_reset:
            ftdi.usb_reset(self._ctx)
        ftdi.read_data_set_chunksize(self._ctx, 65535)
        ftdi.write_data_set_chunksize(self._ctx, 65535)
        # RESET MPSSE
        ftdi.set_bitmode(self._ctx, 0, 0)
        # Enable MPSSE
        ftdi.set_bitmode(self._ctx, 0, 2)
        # Set Latency timer to 16ms
        ftdi.set_latency_timer(self._ctx, 16)

    # Cleanup the FTDI connection and release it.
    def close(self):
        if self._ctx is not None:
            self._debug(3, "MPSSE: Max buffer: {}".format(self._max_buffer))
            self._debug(3, "MPSSE: Closed. FTDI Released")
            ftdi.free(self._ctx)
        self._ctx = None
        self._od = False
        self._rc = False

    # Synchronize the MPSSE engine by sending the bad command and looking through the
    # buffer until we see it's rejection.
    def sync(self):
        self._debug(3, "MPSSE: Sync")
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
        self._debug(3, "MPSSE: Setup Clock")
        commands = bytearray((
            0x8a,   # turn off clock divide by 5.
            0x97,   # turn off adaptive clocking
            0x8d))  # turn off 3-phase clocking
        self._write(str(commands))

    # Read the GPIO state from the MPSSE Directly
    def read_gpio_state(self):
        self._write( self.read_gpio )
        state = self._read(2)
        return state

    # Get the bytes representing the current GPIO state, and return the
    # MPSSE Command needed to set them to this state
    def get_gpio_cmd(self):
        commands = bytearray((
            0x80,                                # write low bytes
            chr(self._level & 0xFF),             # Low Level
            chr(self._direction & 0xFF),         # Low Direction
            0x82,                                # Read high bytes
            chr((self._level >> 8) & 0xFF),      # High Level
            chr((self._direction >> 8) & 0xFF))) # High Direction
        return commands

    # Write the GPIO to the MPSSE
    def write_gpio_state(self):
        self._debug(3, "MPSSE: GPIO: Writing GPIO")
        self._write(str(self.get_gpio_cmd()))

    # Set the GPIO to the state requested and update the self.low, self.high
    # values to take into account the changed pin.
    def set_pin(self, pin, out, high):

        # Update the pin requested.
        self._set_pin(pin, out, high)

        # Update out MPSSE command for 1-wire low
        self._set_pin(self.pin, True, False)
        self.low = self.get_gpio_cmd()

        # Update out MPSSE command for 1-wire high
        self._set_pin(self.pin, False, True)
        self.high = self.get_gpio_cmd()

    # Set the GPIO pin to in/out and high/low
    def _set_pin(self, pin, out, high):
        self._debug(3, "GPIO: Setting Pin: {}, Out: {}, High: {}".format(pin, out, high))
        if out:
            self._direction |= (1 << pin) & 0xFFFF
        else:
            self._direction &= ~(1 << pin) & 0xFFFF
        if high:
            self._level     |= ~(1 << pin) & 0xFFFF
        else:
            self._level     &= ~(1 << pin) & 0xFFFF

    # Here begins the 1-wire stuff

    # Send a 1-wire reset on the GPIO, This makes all slaves listen up for commands.
    # It also detects the presance of the slaves. If nothing responds, then no devices
    # are connected and we return false.
    def reset(self):

        self._debug(2, "1Wire: Reset")
        commands =  self.clock_G + self.high + self.delay + \
                    self.clock_H + self.low + self.delay + self.high + self.clock_I + self.delay + \
                    self.read_gpio + self.clock_J + self.delay + self.read_gpio 

        self._write(str(commands))
        present = self._read(4)

        if present == '\xff'*4:
            if self._od:
                self._debug(2, "1Wire: No Devices in Overdrive mode, trying standard reset");
                self._reset_clocks(False)
                return self.reset()
            else:
                self._debug(2, "1Wire: No Devices Present")
                return False
        else:
            self._debug(2, "1Wire: Devices Present")
            return True

    # A device needs to do some processing, sleep some, and then check for a
    # result. If pullup is defined, we'll ensure that pin is high while we sleep.
    # NB: If we use pin 5 (D5 (GPIOL1)), then we use MPSSE 0x88 and 0x89 to
    # to detect the 1/0 pulses from the slave at completion.
    def pullup_and_check(self, ms=10, commands=""):
        if self._buffer is False:
            raise Exception("You must buffer commands when using pullup_and_check() to ensure correct timing")
        secs = 1.0 * ms / 1000.0
        up = None
        down = None

        # If pullup is defined, then its providing additional power, keep the
        # pin up for the duration of the work.
        if self.pullup is not None:
            self._debug(2, "1Wire: Pullup Enabling additional power via GPIO {}".format(self.pullup))
            self.set_pin(self.pullup, True, True)
            up = self.get_gpio_cmd()
            self.set_pin(self.pullup, False, False)
            down = self.get_gpio_cmd()

        # If we're using GPIOL1 (pin 5) then we can get the MPSSE to wait for the
        # slave to signal completion, if not we just have to sleep.
        #if self.pin is self._gpiol1:
        #   wait_signal = self.clock_Z + bytearray( (0x88, 0x89) )
        #   commands = wait_signal
        #   if up is not None:
        #       commands = up + wait_signal + down
        #   self.flush_command_buffer()
        #   self._debug(2, "1Wire: Pullup Waiting for Signal")
        #   self._write( str( commands ) )
        #else:

        self._debug(2, "1Wire: Pullup Sleeping for {}ms".format(ms))
        if up is not None:
            self._write(str(up))
            self.flush_command_buffer()
            time.sleep( secs )
            self._write(str(down))
        else:
            self.flush_command_buffer()
            time.sleep( secs )

        # Check for a response from the slave
        byte = self.read_byte()
        self._debug(2, "1Wire: Pullup Complete, Returning First Byte: {:x}".format(byte))
        return byte

    # Write a bit to the 1-wire bus, either a 1 or a 0
    def write_bit(self, bit):
        self._debug(4, "1Wire: Write Bit: {}".format(bit))
        if bit:
            commands = self.clock_A + self.low + self.delay + self.high + self.clock_B + self.delay 
        else:
            commands = self.clock_C + self.low + self.delay + self.high + self.clock_D + self.delay

        self._write(str(commands))

    def read_command(self, bits=1):
        for i in range(bits):
            commands = self.clock_A + self.low + self.delay + self.high + self.clock_E +\
                       self.delay + self.read_gpio + self.clock_F + self.delay
            self._write(str(commands))

    def read_response(self, bits=1):
        states = []
        read = self._read(2 * bits)
        for i in range(0,2*bits,2):
            bit = bytearray([read[i], read[i+1]])
            states.append( struct.unpack("H", str(bit))[0] >> self.pin & 01 )
            self._debug(4, "1Wire: Read Bit: {:02x}{:02x} - Pin: {} is {}".format(bit[0],bit[1], self.pin, states[-1]))
        if bits == 1:
            return states.pop()
        return states

    # Read a bit from the 1-wire bus.
    def read_bit(self):
        self.read_command()
        return self.read_response()

    # Use the write_bit function to write bytes out to the bus
    def write_byte(self, byte):
        manage_buffer = self._buffer == False
        self._debug(3, "1Wire: Write Byte: {:02x}, Managed Buffer: {}".format(byte, manage_buffer))
        if manage_buffer:
            self.enable_command_buffer()
        for i in range(8):
            self.write_bit(byte & 1)
            byte >>= 1
        if manage_buffer:
            self.flush_command_buffer()

    # write multiple bytes to the bus
    def write_bytes(self, data):
        if type(data) is str:
            data = bytearray( data )
        try:
            for byte in data:
                self.write_byte(byte)
        except TypeError:
            self.write_byte(data)

    # Use the read_bit function to read bytes from the bus
    def read_byte(self):
        byte = 0
        manage_buffer = self._buffer == False
        if manage_buffer:
            self.enable_command_buffer()
        self.read_command(8)
        if manage_buffer:
            self.flush_command_buffer()
        bits = self.read_response(8)
        for i in range(8):
            byte |= bits[i] << i
        self._debug(3, "1Wire: Read Byte: {:02x}, Managed Buffer: {}".format(byte, manage_buffer))
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
        self._debug(3, "1Wire: Read ROM")
        rom = bytearray(8)
        self.write_byte(0x33)
        for i in range(8):
            rom[i] = self.read_byte()
        self._debug(1, "rom_read discovered: {}".format(self.bytes2string(rom)))
        return rom 

    # Issue a skip rom for overdrive, we can then perform a search at OD speed, or
    # if only one device, send it a command.
    def skip_rom_od(self):
        self._debug(3, "1Wire: Skip ROM OD")
        if self._overdrive:
            self.write_byte(0x3c)
            self._reset_clocks(True)
        else:
            raise Exception("Overdrive is not enabled")

    # There is only one device on the bus so skip ROM matching.
    def skip_rom(self):
        self.write_byte(0xcc)

    # Target the ROM specified
    def _match_rom(self, rom):
        if type(rom) is str:
            rom = self.string2bytes(rom)
        if self._overdrive:
            self.write_byte(0x69)
            self._reset_clocks(True)
        else:
            self.write_byte(0x55)
        self.write_bytes(rom)

    # Address the ROM if given, else perform a skip_rom()
    def address_rom(self, rom):
        if rom is None:
            self._debug(3, "1Wire: Skip ROM")
            self.skip_rom()
        else:
            self._debug(3, "1Wire: Match ROM")
            self._match_rom(rom)

    # Resume, you should only call this if the ROM has been addressed previously
    def resume(self):
        self._debug(3, "1Wire: Resume")
        self.write_byte(0xa5)

    # Search for ROMs on the 1-wire bus
    def search_roms(self):
        roms_found = []
        partials = [ [] ]
        self._debug(1, "Search Start")
        while len(partials) > 0:
            self._debug(1, "Searching....")
            rom = partials.pop()
            roms_found.append( self.bytes2string(self._search(rom, partials)) )
        self._debug(1, "Search Complete")
        return roms_found
        
    # When replaying the partial rom, flush the search out to the MPSSE every 10 bits
    # improves performance.
    def _search_flush_rom(self, count):
        self.flush_command_buffer()
        self.read_response(2*count)
        return 0

    # Do the search for each partial ROM
    def _search(self, rom=[], partials=[]):

        if self.reset() is False:
            return

        # Dump any partial rom to the MPSSE in 10bit chunks
        self.enable_command_buffer()
        self.write_byte(0xf0)
        count = 0
        for bit in rom:
            if count == 10:
                count = self._search_flush_rom(10)
                self.enable_command_buffer()
            count += 1
            self.read_command(2)
            self.write_bit(bit)
        self._search_flush_rom(count)

        # Continue the search from where we are.
        for i in range(64 - len(rom)):
            bits = self.read_bits(2)
            if bits[0] != bits[1]:
                self._debug(3, "Search Match: Found single host or matching bits. Continuing")
                rom.append(bits[0])
                self.write_bit(bits[0])
            elif bits == [False, False]:
                self._debug(2, "Search Fork: Found mismatch. Storing partial. Continuing")
                np = list(rom)
                np.append(True)
                partials.append( np )
                rom.append(False)
                self.write_bit(False)
            else:
                self._debug(1, "Search Fail: Unexpected end of Device Search. No Response from slaves")
                raise Exception("Search Failed. Device Comms Interrupted")

        complete = bytearray(8)
        for i in range(8):
            byte = 0
            for o in range(8):
                bit = rom[(i*8)+o]
                byte |= bit << o
            complete[i] = byte

        self._debug( 1, "Search Found: ROM {}".format( self.bytes2string(complete)))
        if self.crc(complete) is not 0x00:
            raise Exception("CRC Check Failed")
        return complete
        
   # Return an a string representation of the device ROM
    def bytes2string(self, bytesarray):
        return ":".join("{:02x}".format(c) for c in bytesarray)

    # Convert a hexadecimal string to bytes
    def string2bytes(self, string):
        return bytearray(codecs.decode(string.replace(":",""),"hex"))

    # Calculate CRC, result should be 0x00
    def crc(self, data, bits=8):

        if bits == 8:
            poly = 0x8c # x8,x5,x4,+ 1 inverse of 0x131 & 0xff
        elif bits == 16:
            poly = 0xa001 # x16, x15, x2, +1
        else:
            raise Exception("Unsupported CRC length")
        crc = 0x00
        for byte in data:
            for bit in range(8):
                # When bit is on, shift and xor, else just shift
                if ( byte ^ crc) & 0x01:
                    crc >>= 1
                    crc ^= poly
                else:
                    crc >>= 1
                byte >>= 1
        self._debug(3, "CRC Check returned: {:02x}".format(crc))
        return crc

