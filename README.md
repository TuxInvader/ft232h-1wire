1-Wire bus over GPIO on FT232H

Implementation of 1-wire using the Adafruit FT232H Breakout board.

Created using hints and code from:

    https://github.com/adafruit/Adafruit_Python_GPIO
    https://github.com/neenar/pydigitemp

See test files for example usage. The w1ftdi class contains lots of debugging information, so you can get a full
breakdown of the 1-wire and MPSSE commands used. Set the debug to level 5 to get the most verbose output.

## Wiring

Like the Raspbery pi 1-Wire GPIO overlay, you will need a pull up resistor on the GPIO pin. I use a 4k7 pull up to the 5v line on the FT232h. See Image:

![FT232H Wiring](https://raw.githubusercontent.com/TuxInvader/ft232h-1wire/master/resources/wiring.jpg "FT232H wiring")


