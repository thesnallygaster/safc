#!/usr/bin/env python3

import os
import signal
import time

from configparser import ConfigParser

CONFIG_FILE = "/etc/default/safc"

def get_config():
    config = ConfigParser()
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILE}")
    config.read(CONFIG_FILE)
    return config

def parse_fan_curve(fan_curve):
    try:
        fan_curve_parsed = []
        entries = fan_curve.split(",")
        for entry in entries:
            temp, pwm = map(int, entry.split(":"))
            fan_curve_parsed.append((temp, pwm))
        return fan_curve_parsed
    except ValueError:
        raise ValueError(f"Invalid fan curve format; use 'temp1:fan_level1,temp2:fan_level2,...'")

def get_hwmon_path(card):
    hwmon_base_path = f"/sys/class/drm/{card}/device/hwmon"
    if not os.path.exists(hwmon_base_path):
        raise FileNotFoundError(f"hwmon directory for card: {card} not found")

    hwmon_base_path_dirs = os.listdir(hwmon_base_path)
    if not hwmon_base_path_dirs:
        raise FileNotFoundError(f"hwmon entries for card: {card} not found")

    return os.path.join(hwmon_base_path, hwmon_base_path_dirs[0])

def get_hwmon_files(card):
    hwmon_path = get_hwmon_path(card)
    temp_file = os.path.join(hwmon_path, "temp1_input")
    pwm_file = os.path.join(hwmon_path, "pwm1")
    control_file = os.path.join(hwmon_path, "pwm1_enable")

    for file in [temp_file, pwm_file, control_file]:
        if not os.path.exists(file):
            raise FileNotFoundError(f"hwmon file {file} in hwmon path {hwmon_path} not found")

    return temp_file, pwm_file, control_file

def set_pwm_control(control_file, control_mode):
    try:
        with open(control_file, "w") as file:
            file.write(control_mode)
    except Exception as e:
        print(f"Failed to set control mode '{control_mode}' on {control_file}")

def get_pwm(temp, fan_curve):
    for i, (t, pwm) in enumerate(fan_curve):
        if temp < t:
            if i > 0:
                return fan_curve[i - 1][1]
            else:
                return pwm
    return fan_curve[-1][1]

def control_fan(card, fan_curve, temp_hysteresis, adjust_interval):
    temp_file, pwm_file, control_file = get_hwmon_files(card)

    last_adjusted_temp, last_adjusted_pwm = None, None

    def signal_handler(signum, frame):
        set_pwm_control(control_file, "2")
        exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            set_pwm_control(control_file, "1")

            with open(temp_file, "r") as file:
                temp_mili = int(file.read().strip())
            temp = temp_mili / 1000.0

            if (last_adjusted_temp is None or abs(temp - last_adjusted_temp) >= temp_hysteresis):
                pwm = get_pwm(temp, fan_curve)

                if (last_adjusted_pwm is None or abs(pwm - last_adjusted_pwm) > 2):
                    with open(pwm_file, "w") as file:
                        file.write(str(pwm))
                    last_adjusted_pwm = pwm
                    last_adjusted_temp = temp

            time.sleep(adjust_interval)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(adjust_interval)

if __name__ == "__main__":
    try:
        config = get_config()
        card = config.get("safc", "card", fallback="card0")
        fan_curve = parse_fan_curve(config.get("safc", "fan_curve", fallback="0:77,60:102"))
        temp_hysteresis = config.getint("safc", "temp_hysteresis", fallback=3)
        adjust_interval = config.getint("safc", "adjust_interval", fallback=5)
        control_fan(card, fan_curve, temp_hysteresis, adjust_interval)
    except Exception as e:
        print(f"safc error: {e}")
