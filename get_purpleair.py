#!/usr/bin/env python3
"""Demonstrates basic interaction with the PurpleAir API.

Included as a reminder of how one could switch SensorBox from using a built-in
Plantower sensor to reading from PurpleAir instead, then otherwise follow the
identical program flow.
"""

import os
import json

import requests
import pandas

MY_PURPLEAIR = os.environ.get("MY_PURPLEAIR", "37025")

response = requests.get(f"https://www.purpleair.com/json?show={MY_PURPLEAIR}")

print(pandas.DataFrame(response.json().get('results')).T)
