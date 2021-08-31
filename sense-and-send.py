#!/usr/bin/env python3
"""Reads measurements from PMSA300I and sends them to Adafruit IO.
"""

import os
import sys
import time
import argparse

import requests

import board
import busio
import adafruit_pm25.i2c
import Adafruit_IO

SEND_KEYS = {
    "pm10 standard": None,
    "pm25 standard": "m2-dot-5",
    "pm100 standard": None,
    "pm10 env": None,
    "pm25 env": None,
    "pm100 env": None,
    "particles 03um": "03um-particles",
    "particles 05um": "05um-particles",
    "particles 10um": "10um-particles",
    "particles 25um": "25um-particles",
    "particles 50um": "50um-particles",
    "particles 100um": "100um-particles",
    "pm25 aqi": "pm2-dot-5-aqi",
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
    """
    if not aio:
        print(f"Measured {value:.1f} for {feed_name}")
    else:
        print(f"Sending {value:.1f} to {feed_name}")
        feed = aio.feeds(feed_name)
        aio.send_data(feed.key, value)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--username", default=os.environ.get("ADAFRUIT_IO_USERNAME"), help="Adafruit IO username")
    parser.add_argument("-k", "--key", default=os.environ.get("ADAFRUIT_IO_KEY"), help="Adafruit IO key")
    parser.add_argument("-a", "--average-every", default=60, help="interval between reporting average, in seconds")
    parser.add_argument("-s", "--sample-time", default=1, help="seconds between successive sampling")
    args = parser.parse_args()

    i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
    pm25 = adafruit_pm25.i2c.PM25_I2C(i2c, None)

    aio_key = args.key

    aio = None

    measurements = {}
    while True:
        time.sleep(args.sample_time)
        if not aio and args.username and args.key:
            aio = Adafruit_IO.Client(args.username, args.key)

        try:
            aqdata = pm25.read()
        except RuntimeError:
            sys.stderr.write("Unable to read from sensor, retrying\n")
            continue

        keys = list(aqdata.keys()) + ["pm25 aqi"]
        for key in SEND_KEYS:
            if key in aqdata:
                val = aqdata[key]
            elif key == "pm25 aqi" and "pm25 standard" in aqdata:
                val = calculate_aqi(aqdata["pm25 standard"])
            else:
                raise KeyError(f"Unknown metric key {key}")

            if key not in measurements:
                measurements[key] = {
                    "sum": 0.0,
                    "count": 0,
                }
            measurements[key]["last"] = val
            measurements[key]["sum"] += val
            measurements[key]["count"] += 1

        del_keys = set()
        for key, val in measurements.items():
            if val["count"] == args.average_every:
                avg = val["sum"] / val["count"]
                feed = SEND_KEYS.get(key)
                if not feed:
                    continue
                try:
                    send_data(avg, SEND_KEYS[key], aio)
                    del_keys.add(key)
                except requests.exceptions.ConnectionError:
                    sys.stderr.write("Connection to Adafruit IO failed\n")
                    aio = None

        for del_key in del_keys:
            del measurements[del_key]
