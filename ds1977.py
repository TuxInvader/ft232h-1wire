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
    def __init__(self, pin, debug=0, rom=None, pullup=None):

        # super
        super(Ds1977, self).__init__(pin, debug, pullup=pullup, overdrive=True)

        # vars
        self.rom     = rom
        self.passwd  = 0x7f
        self.read    = 0xc0
        self.write   = 0xc8
        self.ctrl    = 0xd0

        # User writable area
        self._first_page   = 0x0000 # 00000
        self._last_page    = 0x7F80 # 32640
        self._last_byte    = 0x7FBF # 32703
        self._pages        = 0x01FF # 511
        self._page_length  = 0x003F # 63

        # Init FTDI 1-Wire
        self.open()
        self.sync()
        self.setup_clock()

        
    def _ready(self):
        if self.reset():
            if self._od is False:
                self.skip_rom_od()
                self.reset()
            if self._rc:
                self.resume()
            else:
                self.address_rom(self.rom)
                self._rc = True
            return True
        return False

    def get_version(self):
        if self._ready():
            self.write_bytes( self.string2bytes("cc0000") )
            data = self.read_bytes(3)
            if data[0] == data[1] and data[2] == 255:
                return ( data[0] >> 5 )
            else:
                raise Exception("Failed to read Version!")

    # Write to scratchpad, if data was a full page (64 bytes) then read the CRC and verify.
    # Returns True if page was full and CRC verified OK, else False
    def write_scratchpad(self, ta1, ta2, data):
        if ( (ta2<<8)+ta1+len(data)-1 ) > self._last_byte:
            raise Exception("Please use change_passwords() and enable_passwords() to manage security.")
        elif len(data) > 64:
            raise Exception("Memory pages are 64 bytes, your data is too long!")
        else:
            if type(data) is str:
                data = bytearray( data )
            self._write_scratchpad(ta1, ta2, data)
            if len(data) == 64:
                # Verify the CRC only if we wrote the entire page
                crc = self.read_bytes(2)
                crc[0] ^= 0xff
                crc[1] ^= 0xff
                check = bytearray((0x0f, ta1, ta2))
                check.extend(data)
                check.extend(crc)
                if self.crc(check, bits=16) != 00:
                    raise Exception("CRC16 Check Failed")
                return True
        return False

    def _write_scratchpad(self, ta1, ta2, data):
        if self._ready():
            self.enable_command_buffer()
            self.write_byte( 0x0f )
            self.write_byte( ta1 )
            self.write_byte( ta2 )
            self.write_bytes( data )
            self.flush_command_buffer()

    # Read Scratchpad and return a tuple representing: (TA1, TA2, ES, DATA)
    def read_scratchpad(self, length):
            data = self._read_scratchpad(length+3)
            return (data[0], data[1], data[2], data[3:])

    def _read_scratchpad(self, length):
        if self._ready():
            self.write_byte( 0xaa )
            data = self.read_bytes(length)
            return data

    # https://datasheets.maximintegrated.com/en/ds/DS1977.pdf "Copy takes 10ms maximum"
    def copy_scratchpad(self, ta1, ta2, esb, password):
        if self._ready():
            self.enable_command_buffer()
            self.write_byte( 0x99 )
            self.write_byte( ta1 )
            self.write_byte( ta2 )
            self.write_byte( esb )
            self.write_bytes( password )
            if self.pullup_and_check(10) is not 0xaa:
                raise Exception("Copy Scratchpad Failed!")

    def clear_scratchpad(self, length):
        if self._ready():
            self.enable_command_buffer()
            data = bytearray(length)
            self.write_byte( 0x0f )
            self.write_byte( 0x00 )
            self.write_byte( 0x00 )
            self.write_bytes( data )
            self.flush_command_buffer()

    def read_pages(self, start, password, number=1):
        pages = self._pages - (start+number)
        if pages < 0 or pages > self._pages:
            raise Exception("DS1977 has 511 (0-510) user addressable pages")
        start = start * 64 
        return self.read_memory(start&0xff, start>>8, password, number)

    # https://datasheets.maximintegrated.com/en/ds/DS1977.pdf "Transfer takes 5ms maximum"
    def read_memory(self, ta1, ta2, password, pages=1):
        if ( (ta2<<8)+ta1 ) > self._last_byte:
            raise Exception("You can't read from there!")
        if self._ready():
            self.write_byte( 0x69 )
            self.write_byte( ta1 )
            self.write_byte( ta2 )
            self.write_bytes( password )
            first_page = int(((ta2<<8)+ta1) / (self._page_length + 1))
            if pages == 0:
                pages = self._pages - first_page 
            page_offset = ((ta2<<8)+ta1) % (self._page_length + 1)
            length = self._page_length - page_offset
            responses = []
            for i in xrange(pages):
                self.enable_command_buffer()
                response = chr( self.pullup_and_check(5) )
                response += self.read_bytes(length)
                crc = self.read_bytes(2)
                crc[0] ^= 0xff
                crc[1] ^= 0xff
                if i == 0:
                    # First page CRC includes command and address. Next pages don't
                    check = bytearray((0x69, ta1, ta2))
                else:
                    check = bytearray()
                check.extend(response)
                check.extend(crc)
                if self.crc(check, bits=16) != 00:
                    raise Exception("CRC16 Check Failed")
                responses.append(response)
                length = self._page_length
        self.reset()
        return responses

    # Verify the password 
    # https://datasheets.maximintegrated.com/en/ds/DS1977.pdf "Transfer takes 5ms maximum"
    def _verify_password(self, ta1, ta2, password):
        if self._ready():
            self.enable_command_buffer()
            self.write_byte(0xc3)
            self.write_byte( ta1 )
            self.write_byte( ta2 )
            self.write_bytes( password )
            if self.pullup_and_check(5) is not 0xaa:
                raise Exception("Verify Password Failed {:x}{:x}!".format(ta1,ta2))

    # change passwords, this will disable the password control first.
    # read_access is the read password to set, full_access is the full access
    # password to set, and current is the current full access password
    def change_passwords(self, read_access, full_access, current):

        # Check Passwords
        if len(read_access) != 8 or len(full_access) != 8:
            raise Exception("Passwords must be 8 bytes")

        # Disable Password First (in case something goes wrong)
        self._debug(1, "Ensuring Passwords are disabled before continuing")
        self.enable_passwords(False, current)
        
        # Send both passwords to scratchpad
        self._debug(1, "Sending passwords to Scratchpad")
        data = bytearray(read_access + full_access)
        self._write_scratchpad(self.read, self.passwd, data)

        # Verify the Scratchpad
        self._debug(1, "Verifying passwords to Scratchpad")
        sp = self._read_scratchpad(19)
        self._debug(2, "SP Contains: {}".format( self.bytes2string(sp) ))
        if list(sp) != list([ self.read, self.passwd, 0x0f ] + [b for b in data]):
            raise Exception("Scratch Pad differs")

        # copy scratchpad to password store
        self._debug(1, "Copying passwords to Register")
        self.copy_scratchpad(self.read, self.passwd, 0x0f, bytearray(current) )

        # verify read password stored correctly
        self._debug(1, "Verify READ Password")
        self._verify_password(self.read, self.passwd, bytearray(read_access) )

        # verify write password stored correctly
        self._debug(1, "Verify WRITE Password")
        self._verify_password(self.write, self.passwd, bytearray(full_access) )

        # Clear the passwords from the SP
        self._debug(1, "Clearing Scratchpad")
        self.clear_scratchpad(16)

    def enable_passwords(self, enable, password):
        if enable:
            flag = 0xaa
        else:
            flag = 0x00

        # Write the flag and verify
        self._debug(1, "Writing password ctrl flag to Scratchpad")
        self._write_scratchpad(self.ctrl, self.passwd, flag)
        self._debug(1, "Verifying")
        sp = self._read_scratchpad(4)
        self._debug(2, "SP Contains: {}".format( self.bytes2string(sp) ))
        if list(sp) != list([ self.ctrl, self.passwd, 0x10, flag ]):
            raise Exception("Scratch Pad differs")

        # copy scratchpad to password store
        self._debug(1, "Copying CTRL flag to Register")
        self.copy_scratchpad(self.ctrl, self.passwd, 0x10, bytearray(password) )

        

