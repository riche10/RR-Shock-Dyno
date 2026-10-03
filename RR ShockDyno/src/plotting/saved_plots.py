from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def save_force_position_plot(df: pd.DataFrame, output_path: Path):
    """
    Saves a force vs position plot as a PNG.
    """

    if df.empty:
        return

    fig, ax = plt.subplots(figsize=(8, 6))

    ax.plot(df["position_in"], df["force_lbf"])

    ax.set_title("Force vs Position")
    ax.set_xlabel("Position (in)")
    ax.set_ylabel("Force (lbf)")
    ax.grid(True)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def save_force_velocity_plot(df: pd.DataFrame, output_path: Path):
    """
    Saves a force vs velocity plot as a PNG.
    """

    if df.empty:
        return

    velocity_column = "calculated_velocity_in_s"

    if velocity_column not in df.columns:
        raise ValueError(f"Missing required column: {velocity_column}")

    fig, ax = plt.subplots(figsize=(8, 6))

    ax.plot(df[velocity_column], df["force_lbf"])

    ax.set_title("Force vs Velocity")
    ax.set_xlabel("Velocity (in/s)")
    ax.set_ylabel("Force (lbf)")
    ax.grid(True)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def save_standard_dyno_plots(df: pd.DataFrame, plots_folder: Path, base_name: str) -> dict:
    """
    Saves the standard dyno plot images.

    Returns a dictionary of plot names to file paths.
    """

    plots_folder.mkdir(parents=True, exist_ok=True)

    force_position_path = plots_folder / f"{base_name}_force_position.png"
    force_velocity_path = plots_folder / f"{base_name}_force_velocity.png"

    save_force_position_plot(df, force_position_path)
    save_force_velocity_plot(df, force_velocity_path)

    return {
        "force_position": force_position_path,
        "force_velocity": force_velocity_path,
    }