#!/usr/bin/env python3
import board
import adafruit_hts221
import adafruit_lps2x
import adafruit_lsm9ds1
from adafruit_bus_device.i2c_device import I2CDevice

i2c = board.I2C()

class SenseHAT():
    def __init__(self, i2c, lps25_address=0x5c, lsm9ds1_mag_address=0x1c, lsm9ds1_xg_address=0x6a, ledmatrix_address=0x46):
        self.hts221 = adafruit_hts221.HTS221(i2c)
        self.lps25 = adafruit_lps2x.LPS25(i2c_bus=i2c, address=lps25_address)
        self.lsm9ds1 = adafruit_lsm9ds1.LSM9DS1_I2C(
            i2c=i2c,
            mag_address=lsm9ds1_mag_address,
            xg_address=lsm9ds1_xg_address)
        self.ledmatrix = LEDMatrix(i2c_bus=i2c, address=ledmatrix_address)

    # self.lsm9ds1.acceleration
    # self.lsm9ds1.magnetic
    # self.lsm9ds1.gyro
    # self.lsm9ds1.temperature
    # self.hts221.relative_humidity
    # self.hts221.temperature
    # self.lps25.pressure
    # self.lps25.temperature

class LEDMatrix:
    def __init__(self, i2c_bus, address=0x46):
        self.i2c_device = I2CDevice(i2c_bus, address)
        self._brightness = 1.0
        self.nrow = 8
        self.ncol = 8
        self.clear()

    def __str__(self):
        output_str = ""
        for y in range(self.nrow):
            for rgb in range(3):
                for x in range(self.ncol):
                    output_str += "0x{:02x}, ".format(self.pixels[y][rgb][x])
                output_str += "\n"
            output_str += "\n"
        return output_str

    @property
    def brightness(self):
        return self._brightness

    @brightness.setter
    def brightness(self, value):
        self._brightness = value % 1.0

    def default_pattern(self):
        self.pixels = DEFAULT_PATTERN

    def clear(self):
        self.pixels = [[[0 for x in range(self.ncol)] for rgb in range(3)] for y in range(self.nrow)]

    def set_pixel(self, x, y, red, green, blue):
        self.pixels[y][0][x] = int(red * 63)
        self.pixels[y][1][x] = int(green * 63)
        self.pixels[y][2][x] = int(blue * 63)

    def shift_l(self):
        for irow, row in enumerate(self.pixels):
            for rgb in row:
                rgb0 = rgb[0]
                for col in range(1, self.ncol):
                    rgb[col - 1] = rgb[col]
                rgb[-1] = rgb0

    def shift_r(self):
        for irow, row in enumerate(self.pixels):
            for rgb in row:
                rgb0 = rgb[-1]
                for col in range(1, self.ncol):
                    rgb[self.ncol - col] = rgb[7 - col]
                rgb[0] = rgb0

    def shift_u(self):
        shift_buf = self.pixels[0]
        for row in range(1, self.nrow):
            self.pixels[row - 1] = self.pixels[row]
        self.pixels[-1] = shift_buf

    def shift_d(self):
        shift_buf = self.pixels[-1]
        for row in range(1, self.nrow):
            self.pixels[self.nrow - row] = self.pixels[7 - row]
        self.pixels[0] = shift_buf

    def update(self):
        with self.i2c_device as display:
            display.write(bytearray([0] + [
                int(x * self.brightness) for x in itertools.chain(
                    *itertools.chain(
                        *self.pixels))]))
