import json
from pathlib import Path


DEFAULT_CALIBRATION = {
    "force": {
        "zero_raw": 0.0,
        "scale_lbf_per_raw": 1.0,
    },
    "position": {
        "zero_raw": 0.0,
        "scale_in_per_raw": 1.0,
    },
}


def load_calibration(config_path: Path) -> dict:
    """
    Loads sensor calibration from JSON.

    If the file does not exist yet, it creates a default calibration file.
    """

    if not config_path.exists():
        save_calibration(config_path, DEFAULT_CALIBRATION)
        return DEFAULT_CALIBRATION.copy()

    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_calibration(config_path: Path, calibration: dict):
    """
    Saves sensor calibration to JSON.
    """

    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as file:
        json.dump(calibration, file, indent=4)


def convert_force_raw_to_lbf(force_raw: float, calibration: dict) -> float:
    """
    Converts raw force sensor value into pounds-force.
    """

    zero_raw = calibration["force"]["zero_raw"]
    scale = calibration["force"]["scale_lbf_per_raw"]

    return (force_raw - zero_raw) * scale


def convert_position_raw_to_in(position_raw: float, calibration: dict) -> float:
    """
    Converts raw position sensor value into inches.
    """

    zero_raw = calibration["position"]["zero_raw"]
    scale = calibration["position"]["scale_in_per_raw"]

    return (position_raw - zero_raw) * scale