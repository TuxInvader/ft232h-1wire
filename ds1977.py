#!/usr/bin/python

# 1-wire over FT232H
# DS1977 32KB iButton (with password) 
#
# 1-wire specs
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/126
# https://www.maximintegrated.com/en/app-notes/index.mvp/id/187
#
# iButton Spec
# https://datasheets.maximintegrated.com/en/ds/DS1977.pdf
#

from w1ftdi import W1ftdi
import time
import struct

class Ds1977(W1ftdi):


    # init
    def __init__(self, pin, debug=0, rom=None):

        # super
        super(Ds1977, self).__init__(pin, debug, overdrive=True)

        # vars
        self.rom     = rom
        self.passwd  = 0x7f
        self.read    = 0xc0
        self.write   = 0xc8
        self.ctrl    = 0xd0
        self._rc     = False

        # Init FTDI 1-Wire
        self.open()
        self.sync()
        self.setup_clock()

        
    def _ready(self):
        if self.reset():
            if self._od is False:
                self.skip_rom_od()
            if self._rc:
                self.resume()
            else:
                self.address_rom(self.rom)
                self._rc = True
            return True
        return False

    def get_version(self):

        # Reset the line, bail if no devices
        if self.reset() is False:
            raise Exception("No Device")

        self.address_rom(self.rom)
        self.write_bytes( self.string2bytes("cc0000") )
        data = self.read_bytes(3)
        if data[0] == data[1] and data[2] == 255:
            return ( data[0] >> 5 )
        else:
            raise Exception("Failed to read Version!")

    def write_scratchpad(self, ta1, ta2, data):
        if ta2 >= 0x7f:
            raise Excpetion("Please use change_password() or enabled_passwords() to manage security.")
        else:
            self._write_scratchpad(ta1, ta2, data)

    def _write_scratchpad(self, ta1, ta2, data):
        if self._ready():
            #self.enable_command_buffer()
            self.write_byte( 0x0f )
            self.write_byte( ta1 )
            self.write_byte( ta2 )
            self.write_bytes( data )
            #self.flush_command_buffer()

    def read_scratchpad(self, length):
        if self._ready():
            #self.enable_command_buffer()
            self.write_byte( 0xaa )
            data = self.read_bytes(length)
            #self.flush_command_buffer()
            return data

    def copy_scratchpad(self, ta1, ta2, esb, password):
        if self._ready():
            #self.enable_command_buffer()
            self.write_byte( 0x99 )
            self.write_byte( ta1 )
            self.write_byte( ta2 )
            self.write_byte( esb )
            self.write_bytes( password )
            #self.flush_command_buffer()
            if self.pullup_and_check() is not 0xaa:
                raise Exception("Copy Scratchpad Failed!")

    def clear_scratchpad(self, length):
        if self._ready():
            data = bytearray(length)
            self.write_byte( 0x0f )
            self.write_byte( 0x00 )
            self.write_byte( 0x00 )
            self.write_bytes( data )

    def verify_password(self, ta1, ta2, password):
        if self._ready():
            self.write_byte(0xc3)
            self.write_byte( ta1 )
            self.write_byte( ta2 )
            self.write_bytes( password )
            if self.pullup_and_check() is not 0xaa:
                raise Exception("Verify Password Failed {:x}{:x}!".format(ta1,ta2))
        
    def change_passwords(self, read_access, full_access, current="DEADBEEF"):


        # Check Passwords
        if len(read_access) != 8 or len(full_access) != 8:
            raise Exception("Passwords must be 8 bytes")
        
        # Send both passwords to scratchpad
        self._debug(1, "Sending passwords to Scratchpad")
        data = bytearray(read_access + full_access)
        self._write_scratchpad(self.read, self.passwd, data)

        # Verify the Scratchpad
        self._debug(1, "Verifying passwords to Scratchpad")
        sp = self.read_scratchpad(19)
        self._debug(2, "SP Contains: {}".format( self.bytes2string(sp) ))
        if list(sp) != list([ self.read, self.passwd, 0x0f ] + [b for b in data]):
            raise Exception("Scratch Pad differs")

        # copy scratchpad to password store
        self._debug(1, "Copying passwords to Register")
        self.copy_scratchpad(self.read, self.passwd, 0x0f, bytearray(current) )

        # verify read password stored correctly
        self._debug(1, "Verify READ Password")
        self.verify_password(self.read, self.passwd, bytearray(read_access) )

        # verify write password stored correctly
        self._debug(1, "Verify WRITE Password")
        self.verify_password(self.write, self.passwd, bytearray(full_access) )

        # Clear the passwords from the SP
        self._debug(1, "Clearing Scratchpad")
        self.clear_scratchpad(16)

    def enable_passwords(self, enabled, password):
        if enabled:
            flag = 0xaa
        else:
            flag = 0x00

        # Write the flag and verify
        self._debug(1, "Writing password ctrl flag to Scratchpad")
        self._write_scratchpad(self.ctrl, self.passwd, flag)
        self._debug(1, "Verifying")
        sp = self.read_scratchpad(4)
        self._debug(2, "SP Contains: {}".format( self.bytes2string(sp) ))
        if list(sp) != list([ self.ctrl, self.passwd, 0x10, flag ]):
            raise Exception("Scratch Pad differs")

        # copy scratchpad to password store
        self._debug(1, "Copying CTRL flag to Register")
        self.copy_scratchpad(self.ctrl, self.passwd, 0x10, bytearray(password) )

        

