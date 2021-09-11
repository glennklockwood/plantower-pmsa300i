#!/usr/bin/env bash
#
#  Script to be called from systemd to set up environment
#

HERE=$(dirname $(readlink -f ${BASH_SOURCE[0]}))

# this file should contain ADAFRUIT_IO_USERNAME and ADAFRUIT_IO_KEY
CONFIG_FILE="$HERE/adafruit-io.sh"

# source this file to get the Python environment in place
ENV_FILE="$HERE/adafruit/bin/activate"

if [ -f "$ENV_FILE" ]; then
    . "$ENV_FILE"
fi
$HERE/sense-and-send.py -f "$CONFIG_FILE" 
