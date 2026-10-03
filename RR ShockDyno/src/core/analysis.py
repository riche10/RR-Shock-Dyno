import pandas as pd
import numpy as np


def process_raw_samples(samples: list[dict]) -> pd.DataFrame:
    """
    Converts recorded shock dyno samples into a processed dataframe.

    Current processing:
    - keeps force_lbf and position_in
    - smooths position
    - calculates velocity from smoothed position vs time
    """

    if not samples:
        return pd.DataFrame()

    df = pd.DataFrame(samples)

    required_columns = ["time_s", "force_lbf", "position_in"]

    for column in required_columns:
        if column not in df.columns:
            raise ValueError(f"Missing required column: {column}")

    df["time_s"] = pd.to_numeric(df["time_s"], errors="coerce")
    df["force_lbf"] = pd.to_numeric(df["force_lbf"], errors="coerce")
    df["position_in"] = pd.to_numeric(df["position_in"], errors="coerce")

    if "velocity_in_s" in df.columns:
        df["velocity_in_s"] = pd.to_numeric(df["velocity_in_s"], errors="coerce")

    df = df.dropna(subset=["time_s", "force_lbf", "position_in"])
    df = df.sort_values("time_s").reset_index(drop=True)

    if len(df) < 2:
        df["smoothed_position_in"] = df["position_in"]
        df["calculated_velocity_in_s"] = 0.0
        return df

    window_size = 5

    df["smoothed_position_in"] = (
        df["position_in"]
        .rolling(window=window_size, center=True, min_periods=1)
        .mean()
    )

    time_values = df["time_s"].to_numpy()
    position_values = df["smoothed_position_in"].to_numpy()

    df["calculated_velocity_in_s"] = np.gradient(position_values, time_values)

    return df


def summarize_processed_data(df: pd.DataFrame) -> dict:
    """
    Creates a simple summary of a processed dyno test.
    """

    if df.empty:
        return {
            "sample_count": 0,
            "duration_s": 0.0,
            "peak_force_lbf": 0.0,
            "min_force_lbf": 0.0,
            "peak_velocity_in_s": 0.0,
            "min_velocity_in_s": 0.0,
        }

    return {
        "sample_count": len(df),
        "duration_s": float(df["time_s"].max() - df["time_s"].min()),
        "peak_force_lbf": float(df["force_lbf"].max()),
        "min_force_lbf": float(df["force_lbf"].min()),
        "peak_velocity_in_s": float(df["calculated_velocity_in_s"].max()),
        "min_velocity_in_s": float(df["calculated_velocity_in_s"].min()),
    }