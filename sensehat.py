#!/usr/bin/env python3
import itertools
import board
import adafruit_hts221
import adafruit_lps2x
import adafruit_lsm9ds1
import adafruit_pm25.i2c
from adafruit_bus_device.i2c_device import I2CDevice

class LEDMatrix:
    def __init__(self, i2c_bus, address=0x46):
        self.i2c_device = I2CDevice(i2c_bus, address)
        self.nrow = 8
        self.ncol = 8
        self.pixels = [[[0 for x in range(self.ncol)] for rgb in range(3)] for y in range(self.nrow)]
        self.clear()

    def __str__(self):
        output_str = ""
        for y in range(self.nrow):
            for rgb in range(3):
                for x in range(self.ncol):
                    output_str += "0x{:02x}, ".format(int(self.pixels[y][rgb][x]))
                output_str += "\n"
            output_str += "\n"
        return output_str

    def default_pattern(self):
        self.pixels = DEFAULT_PATTERN

    def clear(self, red=0.0, green=0.0, blue=0.0):
        #self.pixels = [[[0 for x in range(self.ncol)] for rgb in range(3)] for y in range(self.nrow)]
        for color in red, green, blue:
            if not (0 <= color <= 63):
                raise ValueError(f"red/green/blue must be between 0 and 63 (got {color})")

        #self.pixels = [[[rgb for x in range(self.ncol)] for rgb in [red, green, blue]] for y in range(self.nrow)]
        for row in range(0, self.nrow):
            self.pixels[row][0] = [red] * self.ncol
            self.pixels[row][1] = [green] * self.ncol
            self.pixels[row][2] = [blue] * self.ncol

    def set_pixel(self, x, y, red, green, blue):
        for color in red, green, blue:
            if not (0 <= color <= 63):
                raise ValueError(f"red/green/blue must be between 0 and 63 (got {color})")
        self.pixels[y][0][x] = red
        self.pixels[y][1][x] = green
        self.pixels[y][2][x] = blue
 
    def shift_l(self):
        for row in self.pixels:
            for rgb in row:
                rgb0 = rgb[0]
                for col in range(1, self.ncol):
                    rgb[col - 1] = rgb[col]
                rgb[-1] = rgb0

    def shift_r(self):
        for row in self.pixels:
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
                int(x) for x in itertools.chain(
                    *itertools.chain(
                        *self.pixels))]))

RANGES = [
    (  50, 0x65, 0xe0, 0x43),
    ( 100, 0xff, 0xfe, 0x54),
    ( 150, 0xf0, 0x85, 0x32),
    ( 200, 0xec, 0x33, 0x23),
    ( 300, 0x86, 0x45, 0x93),
    ( 400, 0x74, 0x14, 0x25),
    (9999, 0x74, 0x14, 0x25),
]

RANGES = [
    (   0, 0x00, 0x08, 0x00), # green
    (  50, 0x08, 0x0c, 0x00), # yellow
    ( 100, 0x18, 0x10, 0x00), # orange
    ( 150, 0x18, 0x00, 0x00), # red
    ( 200, 0x10, 0x00, 0x02), # purple
    ( 300, 0x03, 0x00, 0x08), # really purple
    (9999, 0x03, 0x00, 0x08),
]

def aqi2color(aqi):
    last_row = None
    for this_row in RANGES:
        if aqi < this_row[0]:
            break
        last_row = this_row

    if last_row is None:
        return tuple([x for x in this_row[1:]])
    
    ret = []
    for idx in range(1, 4):
        dy = (this_row[idx] - last_row[idx])
        dx = this_row[0] - last_row[0]
        dydx = dy/dx
        b = this_row[idx] - dydx * this_row[0]
        ret.append(abs(dydx*aqi + b)) # take care of -0.0

    return tuple(ret)

def tune_colors_interactive():
    colors = [0, 0, 0]
    while True:
        for idx, color in enumerate(['red', 'green', 'blue']):
            new_c = input("{} (current={:03d}) ".format(color, int(colors[idx])))
            if new_c:
                new_c = int(new_c, 0)
                old_c = colors[idx]
                colors[idx] = new_c
                try:
                    sensehat.ledmatrix.clear(*colors)
                except ValueError:
                    colors[idx] = old_c
                sensehat.ledmatrix.update()

def cycle_aqi():
    import time
    for aqi in range(0, 500, 5):
        red, green, blue = aqi2color(aqi)

        print("{:3d} {:.02f} {:.02f} {:.02f}".format(aqi, red, green, blue))

        sensehat.ledmatrix.clear(red, green, blue)
        sensehat.ledmatrix.update()
        time.sleep(0.05)

if __name__ == "__main__":
    i2c = board.I2C()
    sensehat = SenseHAT(i2c)
    cycle_aqi()
