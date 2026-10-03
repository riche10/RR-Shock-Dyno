"""Offline checks against unchanged source; generated outputs stay in .verification."""
import ast
import hashlib
import importlib.metadata
import json
import math
import os
import sys
import warnings
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
root = Path(__file__).resolve().parent.parent
project = root / "RR ShockDyno"
scratch = root / ".verification"
scratch.mkdir(exist_ok=True)
sys.path.insert(0, str(project))

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from src.core.analysis import process_raw_samples, summarize_processed_data
from src.core.calibration import load_calibration, convert_force_raw_to_lbf, convert_position_raw_to_in
from src.core.motec_analysis import load_motec_shock_csv, calculate_scotch_yoke_rpm, recommend_scotch_yoke_settings, summarize_motec_shock_data
from src.gui.main_window import MainWindow

report = {"hardware_tested": False, "source_changed": False, "python": sys.version,
          "dependencies": {}, "passed_checks": [], "limitations_reproduced": [], "data_inventory": []}
for name in ("PySide6", "shiboken6", "pyqtgraph", "numpy", "pandas", "pyserial", "matplotlib", "scipy"):
    report["dependencies"][name] = importlib.metadata.version(name)
observed_packages = sorted({f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()
                            if d.metadata.get("Name") and d.metadata["Name"].lower() != "pip"}, key=str.lower)
(root / "Verification/requirements-observed.txt").write_text(
    "# Packages observed in the supplied Python environment; not a separately validated clean install.\n" +
    "\n".join(observed_packages) + "\n", encoding="utf-8")

def passed(description):
    report["passed_checks"].append(description)
    print("PASS:", description, flush=True)

python_files = list(project.rglob("*.py"))
for path in python_files:
    ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
passed(f"Syntax parsing: {len(python_files)} original Python files")
for path in sorted((project / "data").rglob("*.csv")):
    df = pd.read_csv(path)
    measurement_columns = [name for name in df.columns if name not in ("corner", "test_name", "operator", "notes")]
    numeric = df[measurement_columns].apply(pd.to_numeric, errors="coerce")
    record = {"path": path.relative_to(project).as_posix(), "rows": len(df), "columns": list(df.columns),
              "nonfinite_measurement_cells": int((~np.isfinite(numeric.to_numpy())).sum()),
              "duplicate_time_values": int(df["time_s"].duplicated().sum()),
              "time_monotonic": bool(df["time_s"].is_monotonic_increasing),
              "duration_s": float(df["time_s"].max() - df["time_s"].min())}
    if path.parent.name == "raw":
        computed = process_raw_samples(df.to_dict("records"))
        paired = pd.read_csv(project / "data/processed" / path.name.replace("_raw.csv", "_processed.csv"))
        record["reprocessed_matches_saved_velocity"] = bool(np.allclose(computed["calculated_velocity_in_s"], paired["calculated_velocity_in_s"], equal_nan=True))
        assert record["reprocessed_matches_saved_velocity"], path
        if {"stroke_setting_in", "velocity_in_s"}.issubset(df.columns):
            residual = df["force_lbf"] - (25 * df["velocity_in_s"] + 8 * (df["position_in"] - df["stroke_setting_in"] / 2))
            record["max_force_residual_from_current_simulator_lbf"] = float(residual.abs().max())
        record["metadata_values"] = {name: sorted(str(x) for x in df[name].dropna().unique())
                                     for name in ("motor_rpm", "stroke_setting_in", "test_name", "operator", "notes") if name in df}
    report["data_inventory"].append(record)
passed(f"Read and inspected {len(report['data_inventory'])} original CSV artifacts")
assert all(r["nonfinite_measurement_cells"] == 0 and r["duplicate_time_values"] == 0 for r in report["data_inventory"])
passed("All saved measurement columns finite; no duplicate timestamps; all nine saved processed velocities reproduced")

assert process_raw_samples([]).empty
assert process_raw_samples([{"time_s": 0, "force_lbf": 1, "position_in": 2}])["calculated_velocity_in_s"].iloc[0] == 0
assert summarize_processed_data(pd.DataFrame())["sample_count"] == 0
try:
    process_raw_samples([{"time_s": 0}])
except ValueError:
    pass
else:
    raise AssertionError("Missing fields accepted")
passed("Empty/single sample analysis and missing-column rejection")

with warnings.catch_warnings():
    warnings.simplefilter("ignore", RuntimeWarning)
    duplicate = process_raw_samples([{"time_s": t, "force_lbf": 0, "position_in": p} for t, p in [(0, 0), (0, 1), (1, 2)]])
assert not np.isfinite(duplicate["calculated_velocity_in_s"]).all()
report["limitations_reproduced"].append("Duplicate timestamps yield nonfinite calculated velocity; original code does not reject duplicates.")

calibration = load_calibration(scratch / "calibration/config.json")
assert convert_force_raw_to_lbf(10, calibration) == 10
assert convert_position_raw_to_in(5, calibration) == 5
passed("Calibration default creation and conversion helpers in isolated directory")

motec_fixture = scratch / "motec_fixture.csv"
motec_fixture.write_text("Synthetic fixture,not vehicle data\nTime,Shock Position FL\ns,mm\n" +
                         "".join(f"{i / 10},{i * 25.4}\n" for i in range(20)), encoding="utf-8")
motec = load_motec_shock_csv(motec_fixture)
assert len(motec) == 20
assert np.allclose(motec["shock_position_in"], np.arange(20))
assert motec.attrs["output_position_units"] == "in"
assert math.isclose(calculate_scotch_yoke_rpm(4 * math.pi, 4), 60)
recommendations = recommend_scotch_yoke_settings(motec)
assert len(recommendations["rpm_recommendations"]) == 30
passed("Synthetic MoTeC import, mm-to-in conversion, and 30 stroke/velocity recommendations")

motec_original = pd.read_csv(next((project / "data/motec_processed").glob("*.csv")))
report["saved_motec_summary"] = summarize_motec_shock_data(motec_original)
assert len(recommend_scotch_yoke_settings(motec_original)["rpm_recommendations"]) == 30
passed("Saved MoTeC processed artifact loads and produces recommendations; raw input not available")

app = QApplication.instance() or QApplication([])
window = MainWindow(scratch / "gui_test")
assert window.tabs.count() == 6
assert not window.connect_teensy_button.isEnabled()
window.show()
app.processEvents()
passed("GUI opens with six tabs and disabled Teensy connection")

with patch("src.data_sources.mock_source.time.time", return_value=100.0):
    window.start_recording()
window.update_timer.stop()
window.data_source.simulation_start_time = 100.0
for i in range(1, 101):
    with patch("src.data_sources.mock_source.time.time", return_value=100.0 + i * .05):
        window.update_live_data()
window.stop_recording()
assert len(window.recorded_samples) == 100
raw_output = scratch / "gui_test/data/raw/verification_raw.csv"
raw_output.parent.mkdir(parents=True, exist_ok=True)
errors = []
with patch.object(QFileDialog, "getSaveFileName", return_value=(str(raw_output), "CSV Files (*.csv)")), \
     patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok), \
     patch.object(QMessageBox, "critical", side_effect=lambda *args: errors.append(str(args))):
    window.save_recording_csv()
assert not errors, errors
processed_output = scratch / "gui_test/data/processed/verification_processed.csv"
processed = pd.read_csv(processed_output)
assert len(processed) == 100
assert len(list((scratch / "gui_test/data/plots").glob("*.png"))) == 2
window.update_analysis_plots(processed)
window.imported_motec_path = motec_fixture
window.update_motec_import_display(motec)
passed("100 simulated GUI samples recorded; raw/processed CSV and both PNG plots saved; analysis and MoTeC displays updated")

original_calibration = dict(window.sensor_calibration)
with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
    window.zero_force()
    window.zero_position()
assert window.sensor_calibration == original_calibration
report["limitations_reproduced"].append("Zero Force and Zero Position only show prototype messages; they do not change calibration.")
window.force_zero_input.setText("2")
with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
    window.save_calibration_from_fields()
assert load_calibration(window.calibration_path)["force"]["zero_raw"] == 2
passed("Calibration fields save/reload in isolated GUI test directory")

window.tabs.setCurrentIndex(0)
app.processEvents()
report["visual_qa_note"] = "Offscreen execution checks widget creation and actions, not normal desktop font rendering or operator usability."
window.update_timer.stop()
window.close()
app.processEvents()

inventory = json.loads((root / "Verification/Original file inventory.json").read_text(encoding="utf-8"))
original = Path(inventory["original_path"])
for record in inventory["files"]:
    if original.is_dir():
        assert hashlib.sha256((original / record["path"]).read_bytes()).hexdigest() == record["sha256"], record["path"]
    if record["included_in_snapshot"]:
        assert hashlib.sha256((project / record["path"]).read_bytes()).hexdigest() == record["sha256"], record["path"]
passed("Preserved project snapshot byte-for-byte identical; original source/environment unchanged when available for comparison")
output = root / "Verification/Software verification.json"
output.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"passed_checks": len(report["passed_checks"]), "report": str(output)}), flush=True)
