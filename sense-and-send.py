#!/usr/bin/env python3
"""Reads measurements from PMSA300I and sends them to Adafruit IO.
"""

import os
import sys
import time
import argparse
import itertools
import warnings
import collections

import board
import busio
import adafruit_hts221
import adafruit_lps2x
import adafruit_lsm9ds1
import adafruit_pm25.i2c

import requests
import Adafruit_IO

from sensehat import LEDMatrix, aqi2color

SEND_KEYS = {
    "pm10 standard": "m1-dot-0",
    "pm25 standard": "m2-dot-5",
    "pm100 standard": "m100",
    "pm10 env": None,
    "pm25 env": None,
    "pm100 env": None,
    "particles 03um": None,
    "particles 05um": None,
    "particles 10um": None,
    "particles 25um": None,
    "particles 50um": None,
    "particles 100um": None,
    "pm25 aqi": "pm2-dot-5-aqi",
    "temperature_hts221": "environmentals.temp-hts221",
    "temperature_lsm9ds1": "environmentals.temp-lsm9ds1",
    "temperature_lps25": "environmentals.temp-lps25",
    "humidity": "environmentals.humidity",
    "pressure": "environmentals.pressure",
}

# from https://aqs.epa.gov/aqsweb/documents/codetables/aqi_breakpoints.html
AQI_BREAKPOINTS = [
    (50, 12),
    (100, 35.4),
    (150, 55.4),
    (200, 150.4),
    (300, 250.4),
    (400, 350.4),
    (500, 500.4),
    (999, 99999.9),
]

class SensorBox():
    def __init__(self, i2c, lps25_address=0x5c, lsm9ds1_mag_address=0x1c, lsm9ds1_xg_address=0x6a, ledmatrix_address=0x46):
        self.pmsa300i = adafruit_pm25.i2c.PM25_I2C(i2c, None)
        self.hts221 = adafruit_hts221.HTS221(i2c)
        self.lps25 = adafruit_lps2x.LPS25(i2c_bus=i2c, address=lps25_address)
        self.lsm9ds1 = adafruit_lsm9ds1.LSM9DS1_I2C(
            i2c=i2c,
            mag_address=lsm9ds1_mag_address,
            xg_address=lsm9ds1_xg_address)
        self.ledmatrix = LEDMatrix(i2c_bus=i2c, address=ledmatrix_address)

        self._measurements = collections.defaultdict(list)
        self._counts = collections.defaultdict(int)

        self._last_pmsa300i_time = None
        self._last_pmsa300i_data = None
        self.max_pmsa300i_freq = 1.0 # seconds
        self._pmsa300i_keys = set([
            "pm10 standard",
            "pm25 standard",
            "pm100 standard",
            "pm10 env",
            "pm25 env",
            "pm100 env",
            "particles 03um",
            "particles 05um",
            "particles 10um",
            "particles 25um",
            "particles 50um",
            "particles 100um",
        ])
        self._function_keys = {
            "pm25 aqi": SensorBox.calculate_pm25_aqi,
            "acceleration": lambda x: x.lsm9ds1.acceleration,
            "magnetic": lambda x: x.lsm9ds1.magnetic,
            "gyro": lambda x: x.lsm9ds1.gyro,
            "temperature_lsm9ds1": lambda x: x.lsm9ds1.temperature,
            "humidity": lambda x: x.hts221.relative_humidity,
            "temperature": lambda x: x.hts221.temperature,
            "temperature_hts221": lambda x: x.hts221.temperature,
            "pressure": lambda x: x.lps25.pressure,
            "temperature_lps25": lambda x: x.lps25.temperature,

        }
        self._sensor_map = {
#           "acceleration": self.lsm9ds1.acceleration,
#           "magnetic": self.lsm9ds1.magnetic,
#           "gyro": self.lsm9ds1.gyro,
#           "temperature_lsm9ds1": self.lsm9ds1.temperature,
#           "humidity": self.hts221.relative_humidity,
#           "temperature": self.hts221.temperature,
#           "temperature_hts221": self.hts221.temperature,
#           "pressure": self.lps25.pressure,
#           "temperature_lps25": self.lps25.temperature,
        }

    def store(self, key, val):
        """Adds a key/value pair to rolling mean
        """
        self._measurements[key].append(val)
        self._counts[key] += 1

    def mean(self, key):
        """Returns rolling mean of a key
        """
        return sum(self._measurements[key]) / self._counts[key]

    def delete(self, key):
        """Deletes all values for key from rolling mean

        Is tolerant of non-existent keys.
        """
        if key in self._measurements:
            del self._measurements[key]
            del self._counts[key]

    def delete_all(self):
        """Delete all keys and values from rolling mean
        """
        for key in self.keys():
            self.delete(key)

    def keys(self):
        """Return iterator with all possible keys
        """
        return itertools.chain(
            self._sensor_map.keys(), 
            self._function_keys.keys(),
            self._pmsa300i_keys)

    def count(self, key):
        """Returns number of values in rolling average
        """
        return self._counts[key]

    def _read_pmsa300i(self, key):
        """Retrieves measurements from PMSA300I

        Raises:
            RuntimeError: if sensor reading fails
        """
        if self._last_pmsa300i_time is None \
        or (time.time() - self._last_pmsa300i_time) >= self.max_pmsa300i_freq:
            self._last_pmsa300i_data = self.pmsa300i.read()
            self._last_pmsa300i_time = time.time()
        
        return self._last_pmsa300i_data.get(key)

    def read_only(self, key):
        """Read from sensor but do not store its value

        Raises:
            KeyError: if key is unknown
        """
        if key in self._pmsa300i_keys:
            return self._read_pmsa300i(key)

        if key in self._function_keys:
            return self._function_keys[key](self)

        return self._sensor_map[key]

    def read(self, key):
        """Read from sensor and retain its value for the rolling mean
        """
        value = self.read_only(key)
        self.store(key, value)
        return value

    def read_all(self):
        ret = {}
        for key in self.keys():
            ret[key] = self.read(key)
        return ret

    def calculate_pm25_aqi(self):
        return calculate_aqi(self.read_only("pm25 standard"))

def calculate_aqi(conc, breakpoints=AQI_BREAKPOINTS):
    """Calculates AQI from PM2.5 concentration

    Args:
        conc (float): PM2.5 in units of ug/m^3
        breakpoints (list): Elements are tuple of (High AQI, High Breakpoint)
            containing all the breakpoints to be used to calculate AQI.

    Returns:
        float: Calculated AQI
    """
    aqi_min, conc_min = (0, 0.0)
    for aqi_max, conc_max in breakpoints:
        if aqi_max is None or conc <= conc_max:
            break
        aqi_min, conc_min = (aqi_max, conc_max)

    aqi = (conc - conc_min) / (conc_max - conc_min) * (aqi_max - aqi_min) + aqi_min
    return aqi

def send_data(value, feed_name, aio):
    """Send or report a value to Adafruit IO

    Args:
        value: Value to send
        feed_name (str): Feed key on Adafruit IO to which value should be sent
            aio: Adafruit IO connection or None

    Returns:
        str or None: Adafruit IO feed to which data was sent, if any
    """
    if not aio or not feed_name:
        return None

    feed = aio.feeds(feed_name)
    aio.send_data(feed.key, value)
    return feed.key

def load_config_file(config_file):
    """Reads config file and passes back findings.

    Args:
        config_file (str): Path to config file to load

    Returns:
        dict: key/value pairs loaded from configuration
    """
    results = {}
    with open(config_file, "r") as cfgfile:
        for line in cfgfile:
            key, val = line.split("=", 1)
            if key.startswith("export "):
                key = key.split(None, 1)[-1]
            val = val.strip().strip("\"")
            key = key.strip()
            results[key] = val
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--config-file", default=None, type=str, help="config file containing adafruit io credentials")
    parser.add_argument("-u", "--username", default=None, help="Adafruit IO username")
    parser.add_argument("-k", "--key", default=None, help="Adafruit IO key")
    parser.add_argument("-a", "--average-every", type=int, default=60, help="interval between reporting average, in seconds")
    parser.add_argument("-s", "--sample-time", type=int, default=1, help="seconds between successive sampling")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="limit output")
    parser.add_argument("-t", "--trailing-mean", type=int, default=10, help="number of samples to include in trailing mean for LED color")
    args = parser.parse_args()

    i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
    sensorbox = SensorBox(i2c)
    aio = None
    print("Connected to all sensors")

    # get adafruit io user/pass
    config = {}
    if args.config_file:
        config = load_config_file(args.config_file)
    # first read from environment
    if "ADAFRUIT_IO_USERNAME" in os.environ:
        if args.verbose: print("Using ADAFRUIT_IO_USERNAME from environment")
        adafruit_user = os.environ["ADAFRUIT_IO_USERNAME"]
    if "ADAFRUIT_IO_KEY" in os.environ:
        if args.verbose: print("Using ADAFRUIT_IO_KEY from environment")
        adafruit_key = os.environ["ADAFRUIT_IO_KEY"]

    # then load from config file
    adafruit_user = config.get("ADAFRUIT_IO_USERNAME")
    adafruit_key = config.get("ADAFRUIT_IO_KEY")

    # then use whatever was passed explicitly on the command line
    if args.username:
        adafruit_user = args.username
    if args.key:
        adafruit_key = args.key

    trailing_mean = None
    trailing_iter = 0
    if args.trailing_mean:
        trailing_mean = [0] * args.trailing_mean

    while True:
        time.sleep(args.sample_time)
        if not aio and adafruit_user and adafruit_key:
            aio = Adafruit_IO.Client(adafruit_user, adafruit_key)

        for key, feed in SEND_KEYS.items():
            # don't bother measuring values we don't send
            if not feed:
                continue

            # try taking measurement
            try:
                val = sensorbox.read(key)
            except RuntimeError:
                warnings.warn("Sensor read failed")
                continue

            if args.verbose: print(f"sensed {key} = {val}, count={sensorbox.count(key)}")

            # update rolling average and update LED display if enabled
            if trailing_mean and key == "pm25 aqi":
                trailing_mean[trailing_iter] = val
                trailing_iter = (trailing_iter + 1) % args.trailing_mean
                colors = aqi2color(sum(trailing_mean) / args.trailing_mean)
                sensorbox.ledmatrix.clear(*colors)
                sensorbox.ledmatrix.update()

            # calculate mean, send, and reset if we've got enough measurements
            if sensorbox.count(key) == args.average_every:
                mean_val = sensorbox.mean(key)
                sensorbox.delete(key)
                # only update LED matrix here if we aren't updating it based on
                # trailing mean
                if key == "pm25 aqi" and not args.trailing_mean:
                    colors = aqi2color(mean_val)
                    sensorbox.ledmatrix.clear(*colors)
                    sensorbox.ledmatrix.update()

                try:
                    feed_key = send_data(mean_val, feed, aio)
                    if not args.quiet:
                        if feed_key:
                            print(f"Sending {mean_val:.1f} to {feed_key}")
                        else:
                            print(f"Measured {mean_val:.1f} for {feed}")
                except (IOError, Adafruit_IO.errors.AdafruitIOError):
                    warnings.warn("Connection to Adafruit IO failed")
                    aio = None
                except ValueError:
                    warnings.warn("Adafruit IO returned invalid response")
                    aio = None
