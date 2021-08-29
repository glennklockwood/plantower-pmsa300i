#!/usr/bin/env python3

import os
import time
import board
import busio
import adafruit_pm25.i2c
import Adafruit_IO

SEND_KEY = "pm25 standard"
SEND_EVERY = 15

def send_data(value, feed_name, aio):
    if not aio:
        return
    print(f"Sending {value} to {feed_name}")
    feed = aio.feeds(feed_name)
    aio.send_data(feed.key, value)

if __name__ == "__main__":
    i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
    pm25 = adafruit_pm25.i2c.PM25_I2C(i2c, None)

    aio_username = os.environ.get("ADAFRUIT_IO_USERNAME")
    aio_key = os.environ.get("ADAFRUIT_IO_KEY")
    if aio_username and aio_key:
        aio = Adafruit_IO.Client(aio_username, aio_key)
        print("Connecting To Adafruit IO")
    else:
        aio = None
        print("Not connecting To Adafruit IO")

    measurements = {}
    while True:
        time.sleep(1)

        try:
            aqdata = pm25.read()
        except RuntimeError:
            print("Unable to read from sensor, retrying...")
            continue

        for key, val in aqdata.items():
            if key not in measurements:
                measurements[key] = {
                    "sum": 0.0,
                    "count": 0,
                }
            measurements[key]["last"] = val
            measurements[key]["sum"] += val
            measurements[key]["count"] += 1
        if SEND_KEY in measurements:
            print(measurements[SEND_KEY])

        del_keys = set()
        for key, val in measurements.items():
            if val["count"] == SEND_EVERY:
                avg = val["sum"] / val["count"]
                if key == SEND_KEY:
                    send_data(avg, "m2-dot-5", aio)
                del_keys.add(key)

        for del_key in del_keys:
            del measurements[del_key]
