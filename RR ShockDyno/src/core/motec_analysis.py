import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd



def find_motec_header_row(csv_path: Path) -> tuple[int, list[str]]:
    """
    Finds the row where MoTeC channel names begin.

    Example:
    Time, Shock Position FL
    """

    with open(csv_path, "r", encoding="utf-8-sig", errors="replace", newline="") as file:
        reader = csv.reader(file)

        for row_index, row in enumerate(reader):
            cleaned_row = [str(value).strip() for value in row]

            if cleaned_row and cleaned_row[0] == "Time":
                return row_index, cleaned_row

    raise ValueError("Could not find MoTeC data header row starting with 'Time'.")


def read_motec_units(csv_path: Path, header_row_index: int, headers: list[str]) -> dict:
    """
    Reads the units row directly below the channel name row.

    Example:
    Time, Shock Position FL
    s,    in
    """

    with open(csv_path, "r", encoding="utf-8-sig", errors="replace", newline="") as file:
        rows = list(csv.reader(file))

    unit_row_index = header_row_index + 1

    if unit_row_index >= len(rows):
        return {}

    unit_row = [str(value).strip() for value in rows[unit_row_index]]

    units = {}

    for column_name, unit_name in zip(headers, unit_row):
        units[column_name] = unit_name

    return units


def load_motec_shock_csv(csv_path, position_column: str | None = None) -> pd.DataFrame:
    """
    Loads a MoTeC-style shock position CSV.

    Output columns:
    - time_s
    - shock_position_in
    - smoothed_shock_position_in
    - shock_velocity_in_s
    """

    csv_path = Path(csv_path)

    header_row_index, headers = find_motec_header_row(csv_path)
    units = read_motec_units(csv_path, header_row_index, headers)

    raw_df = pd.read_csv(
        csv_path,
        skiprows=header_row_index,
        encoding="utf-8-sig",
        low_memory=False,
    )

    raw_df.columns = [str(column).strip() for column in raw_df.columns]

    time_column = "Time"

    if time_column not in raw_df.columns:
        raise ValueError("MoTeC CSV is missing a Time column.")

    if position_column is None:
        shock_position_columns = [
            column for column in raw_df.columns
            if column != time_column
            and "shock" in column.lower()
            and "position" in column.lower()
        ]

        if shock_position_columns:
            position_column = shock_position_columns[0]
        else:
            possible_columns = [
                column for column in raw_df.columns
                if column != time_column
            ]

            if not possible_columns:
                raise ValueError("No shock position column found.")

            position_column = possible_columns[0]

    if position_column not in raw_df.columns:
        raise ValueError(f"Column not found: {position_column}")

    df = pd.DataFrame()

    df["time_s"] = pd.to_numeric(raw_df[time_column], errors="coerce")

    position_raw = pd.to_numeric(raw_df[position_column], errors="coerce")
    position_unit = units.get(position_column, "").strip().lower()

    if position_unit in ("mm", "millimeter", "millimeters"):
        df["shock_position_in"] = position_raw / 25.4
        output_position_unit = "in"
    else:
        df["shock_position_in"] = position_raw
        output_position_unit = position_unit or "in"

    df = df.dropna(subset=["time_s", "shock_position_in"])
    df = df.sort_values("time_s").reset_index(drop=True)

    if len(df) < 2:
        df["smoothed_shock_position_in"] = df["shock_position_in"]
        df["shock_velocity_in_s"] = 0.0
    else:
        window_size = 5

        df["smoothed_shock_position_in"] = (
            df["shock_position_in"]
            .rolling(window=window_size, center=True, min_periods=1)
            .mean()
        )

        df["shock_velocity_in_s"] = np.gradient(
            df["smoothed_shock_position_in"].to_numpy(),
            df["time_s"].to_numpy(),
        )

    df.attrs["source_file"] = str(csv_path)
    df.attrs["source_position_column"] = position_column
    df.attrs["source_position_units"] = units.get(position_column, "")
    df.attrs["output_position_units"] = output_position_unit

    return df


def summarize_motec_shock_data(df: pd.DataFrame) -> dict:
    """
    Creates a simple summary for imported MoTeC shock position data.
    """

    if df.empty:
        return {
            "sample_count": 0,
            "duration_s": 0.0,
            "min_position_in": 0.0,
            "max_position_in": 0.0,
            "travel_used_in": 0.0,
            "max_positive_velocity_in_s": 0.0,
            "max_negative_velocity_in_s": 0.0,
        }

    min_position = float(df["shock_position_in"].min())
    max_position = float(df["shock_position_in"].max())

    return {
        "sample_count": len(df),
        "duration_s": float(df["time_s"].max() - df["time_s"].min()),
        "min_position_in": min_position,
        "max_position_in": max_position,
        "travel_used_in": max_position - min_position,
        "max_positive_velocity_in_s": float(df["shock_velocity_in_s"].max()),
        "max_negative_velocity_in_s": float(df["shock_velocity_in_s"].min()),
    }
def calculate_scotch_yoke_rpm(target_velocity_in_s: float, stroke_in: float) -> float:
    """
    Calculates the motor RPM needed for a Scotch yoke dyno to reach
    a target peak shaft velocity.

    Scotch yoke peak velocity:
    velocity = stroke * pi * rpm / 60

    Solved for rpm:
    rpm = velocity * 60 / (pi * stroke)
    """

    if stroke_in <= 0:
        return 0.0

    return abs(target_velocity_in_s) * 60.0 / (math.pi * stroke_in)


def recommend_scotch_yoke_settings(
    df: pd.DataFrame,
    stroke_options: list[float] | None = None,
    minimum_motion_velocity_in_s: float = 1.0,
) -> dict:
    """
    Uses imported MoTeC shock velocity data to suggest Scotch yoke dyno RPMs.

    Important:
    MoTeC files often include lots of time where the car is sitting still.
    If we include all of that still time, the velocity percentiles become too low.

    So this function focuses on samples where the shock is actually moving.
    """

    if stroke_options is None:
        stroke_options = [2.0, 4.0, 6.0, 8.0, 10.0]

    if df.empty or "shock_velocity_in_s" not in df.columns:
        return {
            "velocity_targets": {},
            "rpm_recommendations": [],
            "motion_sample_count": 0,
            "total_sample_count": 0,
            "motion_percent": 0.0,
            "minimum_motion_velocity_in_s": minimum_motion_velocity_in_s,
        }

    abs_velocity_all = (
        pd.to_numeric(df["shock_velocity_in_s"], errors="coerce")
        .abs()
        .dropna()
    )

    if abs_velocity_all.empty:
        return {
            "velocity_targets": {},
            "rpm_recommendations": [],
            "motion_sample_count": 0,
            "total_sample_count": 0,
            "motion_percent": 0.0,
            "minimum_motion_velocity_in_s": minimum_motion_velocity_in_s,
        }

    moving_velocity = abs_velocity_all[
        abs_velocity_all >= minimum_motion_velocity_in_s
    ]

    # If the filter is too aggressive, fall back to all velocity data.
    if len(moving_velocity) < 10:
        velocity_for_targets = abs_velocity_all
    else:
        velocity_for_targets = moving_velocity

    total_sample_count = len(abs_velocity_all)
    motion_sample_count = len(moving_velocity)
    motion_percent = (motion_sample_count / total_sample_count) * 100.0

    velocity_targets = {
        "50% moving speed": float(np.percentile(velocity_for_targets, 50)),
        "75% moving speed": float(np.percentile(velocity_for_targets, 75)),
        "90% moving speed": float(np.percentile(velocity_for_targets, 90)),
        "95% moving speed": float(np.percentile(velocity_for_targets, 95)),
        "99% moving speed": float(np.percentile(velocity_for_targets, 99)),
        "Peak observed": float(abs_velocity_all.max()),
    }

    rpm_recommendations = []

    for target_name, target_velocity in velocity_targets.items():
        for stroke_in in stroke_options:
            rpm = calculate_scotch_yoke_rpm(
                target_velocity_in_s=target_velocity,
                stroke_in=stroke_in,
            )

            rpm_recommendations.append(
                {
                    "target_name": target_name,
                    "target_velocity_in_s": target_velocity,
                    "stroke_in": stroke_in,
                    "rpm": rpm,
                }
            )

    return {
        "velocity_targets": velocity_targets,
        "rpm_recommendations": rpm_recommendations,
        "motion_sample_count": motion_sample_count,
        "total_sample_count": total_sample_count,
        "motion_percent": motion_percent,
        "minimum_motion_velocity_in_s": minimum_motion_velocity_in_s,
    }