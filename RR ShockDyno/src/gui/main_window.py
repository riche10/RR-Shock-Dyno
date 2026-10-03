import csv
import math
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..data_sources.mock_source import MockDynoSource
from ..core.analysis import process_raw_samples, summarize_processed_data
from ..core.calibration import load_calibration, save_calibration
from ..core.motec_analysis import (load_motec_shock_csv,summarize_motec_shock_data, recommend_scotch_yoke_settings,)
from ..plotting.saved_plots import save_standard_dyno_plots




class MainWindow(QMainWindow):
    def __init__(self, project_root: Path):
        super().__init__()

        self.project_root = project_root

        self.calibration_path = self.project_root / "config" / "sensor_calibration.json"
        self.sensor_calibration = load_calibration(self.calibration_path)

        self.setWindowTitle("RR Shock Dyno")
        self.resize(1200, 800)

        # Recording state
        self.is_recording = False
        self.recorded_samples = []
        self.test_start_time = None

        # Motec Import
        self.imported_motec_df = None
        self.imported_motec_path = None

        # Data source
        self.data_source = MockDynoSource()

        # Live plot buffers
        self.plot_time = []
        self.plot_force = []
        self.plot_position = []
        self.plot_velocity = []

        self.max_plot_points = 500

        # Timer for live updates
        self.update_timer = QTimer()
        self.update_timer.setInterval(50)  # 20 updates per second for GUI display
        self.update_timer.timeout.connect(self.update_live_data)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.live_test_tab = self.build_live_test_tab()
        self.analysis_tab = self.build_analysis_tab()
        self.import_tab = self.build_motec_import_tab()
        self.calibration_tab = self.build_calibration_tab()
        self.settings_tab = self.build_placeholder_tab("Settings")
        self.help_tab = self.build_help_tab()
        self.analysis_tab = self.build_analysis_tab()
        self.tabs.addTab(self.live_test_tab, "Live Test")
        self.tabs.addTab(self.analysis_tab, "Analyze Data")
        self.tabs.addTab(self.import_tab, "Import MoTeC")
        self.tabs.addTab(self.calibration_tab, "Calibration")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.help_tab, "Help")

        self.update_expected_velocity()


    def build_live_test_tab(self) -> QWidget:
        page = QWidget()
        main_layout = QVBoxLayout()

        title = QLabel("Live Shock Dyno Test")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")

        subtitle = QLabel("Prototype mode: simulated Scotch yoke dyno data")
        subtitle.setStyleSheet("font-size: 14px; color: gray;")

        main_layout.addWidget(title)
        main_layout.addWidget(subtitle)

        # -------------------------
        # Test setup section
        # -------------------------
        setup_form = QFormLayout()

        self.test_name_input = QLineEdit()
        self.test_name_input.setPlaceholderText("Example: RR shock clicker 5")

        self.operator_input = QLineEdit()
        self.operator_input.setPlaceholderText("Operator name")

        self.corner_input = QComboBox()
        self.corner_input.addItems(["FL", "FR", "RL", "RR", "Bench/Other"])

        self.stroke_combo = QComboBox()
        self.stroke_combo.addItems(["2", "4", "6", "8", "10"])
        self.stroke_combo.setCurrentText("4")
        self.stroke_combo.currentTextChanged.connect(self.update_expected_velocity)

        self.rpm_input = QLineEdit()
        self.rpm_input.setText("60")
        self.rpm_input.textChanged.connect(self.update_expected_velocity)

        self.expected_velocity_label = QLabel("Expected peak velocity: -- in/s")

        setup_form.addRow("Test name:", self.test_name_input)
        setup_form.addRow("Operator:", self.operator_input)
        setup_form.addRow("Corner:", self.corner_input)
        setup_form.addRow("Scotch yoke stroke setting:", self.stroke_combo)
        setup_form.addRow("Motor RPM:", self.rpm_input)
        setup_form.addRow("Calculated:", self.expected_velocity_label)

        main_layout.addLayout(setup_form)

        # -------------------------
        # Buttons
        # -------------------------
        button_row = QHBoxLayout()

        self.use_sim_button = QPushButton("Use Simulated Data")
        self.connect_teensy_button = QPushButton("Connect Teensy")
        self.zero_force_button = QPushButton("Zero Force")
        self.zero_position_button = QPushButton("Zero Position")
        self.start_button = QPushButton("Start Recording")
        self.stop_button = QPushButton("Stop Recording")
        self.save_button = QPushButton("Save CSV")

        self.connect_teensy_button.setEnabled(False)  # Later feature
        self.stop_button.setEnabled(False)
        self.save_button.setEnabled(False)

        self.use_sim_button.clicked.connect(self.start_simulation_mode)
        self.zero_force_button.clicked.connect(self.zero_force)
        self.zero_position_button.clicked.connect(self.zero_position)
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        self.save_button.clicked.connect(self.save_recording_csv)

        button_row.addWidget(self.use_sim_button)
        button_row.addWidget(self.connect_teensy_button)
        button_row.addWidget(self.zero_force_button)
        button_row.addWidget(self.zero_position_button)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        button_row.addWidget(self.save_button)

        main_layout.addLayout(button_row)

        # -------------------------
        # Live values
        # -------------------------
        self.force_label = QLabel("Force: 0.0 lbf")
        self.position_label = QLabel("Position: 0.0 in")
        self.velocity_label = QLabel("Velocity: 0.0 in/s")
        self.sample_count_label = QLabel("Samples recorded: 0")
        self.status_label = QLabel("Status: Idle")

        live_value_style = "font-size: 20px; font-weight: bold;"

        self.force_label.setStyleSheet(live_value_style)
        self.position_label.setStyleSheet(live_value_style)
        self.velocity_label.setStyleSheet(live_value_style)
        self.sample_count_label.setStyleSheet("font-size: 16px;")
        self.status_label.setStyleSheet("font-size: 16px; color: gray;")

        main_layout.addWidget(self.force_label)
        main_layout.addWidget(self.position_label)
        main_layout.addWidget(self.velocity_label)
        main_layout.addWidget(self.sample_count_label)
        main_layout.addWidget(self.status_label)

        # -------------------------
        # Live plots
        # -------------------------
        main_layout.addWidget(self.build_live_plots_panel())

        # -------------------------
        # Notes
        # -------------------------
        self.notes_box = QTextEdit()
        self.notes_box.setMaximumHeight(90)
        self.notes_box.setPlaceholderText(
            "Test notes: shock settings, oil temp, clickers, spring/no spring, weird noises, etc."
        )

        main_layout.addWidget(QLabel("Test notes:"))
        main_layout.addWidget(self.notes_box)

        page.setLayout(main_layout)
        return page

    def build_live_plots_panel(self) -> QWidget:
        panel = QWidget()
        layout = QGridLayout()

        self.force_time_plot = pg.PlotWidget(title="Force vs Time")
        self.position_time_plot = pg.PlotWidget(title="Position vs Time")
        self.force_position_plot = pg.PlotWidget(title="Force vs Position")
        self.force_velocity_plot = pg.PlotWidget(title="Force vs Velocity")

        self.force_time_plot.setLabel("left", "Force", units="lbf")
        self.force_time_plot.setLabel("bottom", "Time", units="s")

        self.position_time_plot.setLabel("left", "Position", units="in")
        self.position_time_plot.setLabel("bottom", "Time", units="s")

        self.force_position_plot.setLabel("left", "Force", units="lbf")
        self.force_position_plot.setLabel("bottom", "Position", units="in")

        self.force_velocity_plot.setLabel("left", "Force", units="lbf")
        self.force_velocity_plot.setLabel("bottom", "Velocity", units="in/s")

        self.force_time_curve = self.force_time_plot.plot()
        self.position_time_curve = self.position_time_plot.plot()
        self.force_position_curve = self.force_position_plot.plot()
        self.force_velocity_curve = self.force_velocity_plot.plot()

        layout.addWidget(self.force_time_plot, 0, 0)
        layout.addWidget(self.position_time_plot, 0, 1)
        layout.addWidget(self.force_position_plot, 1, 0)
        layout.addWidget(self.force_velocity_plot, 1, 1)

        panel.setLayout(layout)
        return panel

    def build_analysis_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Analyze Saved Dyno Test")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")

        subtitle = QLabel("Open a processed CSV file and view dyno plots.")
        subtitle.setStyleSheet("font-size: 14px; color: gray;")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        button_row = QHBoxLayout()

        self.open_processed_csv_button = QPushButton("Open Processed CSV")
        self.clear_analysis_button = QPushButton("Clear Analysis")

        self.open_processed_csv_button.clicked.connect(self.open_processed_csv)
        self.clear_analysis_button.clicked.connect(self.clear_analysis_plots)

        button_row.addWidget(self.open_processed_csv_button)
        button_row.addWidget(self.clear_analysis_button)

        layout.addLayout(button_row)

        self.analysis_file_label = QLabel("No processed CSV loaded")
        self.analysis_file_label.setStyleSheet("font-size: 14px; color: gray;")

        self.analysis_summary_label = QLabel("Summary will appear here after loading a test.")
        self.analysis_summary_label.setStyleSheet("font-size: 16px;")

        layout.addWidget(self.analysis_file_label)
        layout.addWidget(self.analysis_summary_label)

        plot_grid = QGridLayout()

        self.analysis_force_position_plot = pg.PlotWidget(title="Force vs Position")
        self.analysis_force_velocity_plot = pg.PlotWidget(title="Force vs Velocity")

        self.analysis_force_position_plot.setLabel("left", "Force", units="lbf")
        self.analysis_force_position_plot.setLabel("bottom", "Position", units="in")

        self.analysis_force_velocity_plot.setLabel("left", "Force", units="lbf")
        self.analysis_force_velocity_plot.setLabel("bottom", "Velocity", units="in/s")

        self.analysis_force_position_curve = self.analysis_force_position_plot.plot()
        self.analysis_force_velocity_curve = self.analysis_force_velocity_plot.plot()

        plot_grid.addWidget(self.analysis_force_position_plot, 0, 0)
        plot_grid.addWidget(self.analysis_force_velocity_plot, 0, 1)

        layout.addLayout(plot_grid)

        page.setLayout(layout)
        return page



    def build_calibration_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Sensor Calibration")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")

        subtitle = QLabel(
            "Edit sensor calibration values. Later, this page will guide users through zeroing and known-load calibration."
        )
        subtitle.setStyleSheet("font-size: 14px; color: gray;")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()

        self.force_zero_input = QLineEdit()
        self.force_scale_input = QLineEdit()
        self.position_zero_input = QLineEdit()
        self.position_scale_input = QLineEdit()

        form.addRow("Force zero raw:", self.force_zero_input)
        form.addRow("Force scale, lbf per raw count:", self.force_scale_input)
        form.addRow("Position zero raw:", self.position_zero_input)
        form.addRow("Position scale, inches per raw count:", self.position_scale_input)

        layout.addLayout(form)

        button_row = QHBoxLayout()

        self.load_calibration_button = QPushButton("Reload Calibration")
        self.save_calibration_button = QPushButton("Save Calibration")

        self.load_calibration_button.clicked.connect(self.reload_calibration_fields)
        self.save_calibration_button.clicked.connect(self.save_calibration_from_fields)

        button_row.addWidget(self.load_calibration_button)
        button_row.addWidget(self.save_calibration_button)

        layout.addLayout(button_row)

        help_text = QLabel(
            "Current simple formula:\n"
            "force_lbf = (force_raw - force_zero_raw) × force_scale\n"
            "position_in = (position_raw - position_zero_raw) × position_scale\n\n"
            "For now, these values are manually entered. Once the Teensy is connected, "
            "the Zero Force and Zero Position buttons can automatically fill in the zero values."
        )
        help_text.setStyleSheet("font-size: 14px;")

        layout.addWidget(help_text)

        page.setLayout(layout)

        self.reload_calibration_fields()

        return page


    def build_motec_import_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Import MoTeC Shock Data")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")

        subtitle = QLabel(
            "Open a MoTeC CSV export and convert shock position data into a usable analysis file."
        )
        subtitle.setStyleSheet("font-size: 14px; color: gray;")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        button_row = QHBoxLayout()

        self.open_motec_csv_button = QPushButton("Open MoTeC CSV")
        self.save_motec_processed_button = QPushButton("Save Imported CSV")
        self.clear_motec_button = QPushButton("Clear Import")

        self.save_motec_processed_button.setEnabled(False)

        self.open_motec_csv_button.clicked.connect(self.open_motec_csv)
        self.save_motec_processed_button.clicked.connect(self.save_motec_processed_csv)
        self.clear_motec_button.clicked.connect(self.clear_motec_import_display)

        button_row.addWidget(self.open_motec_csv_button)
        button_row.addWidget(self.save_motec_processed_button)
        button_row.addWidget(self.clear_motec_button)

        layout.addLayout(button_row)

        self.motec_file_label = QLabel("No MoTeC CSV loaded")
        self.motec_file_label.setStyleSheet("font-size: 14px; color: gray;")

        self.motec_summary_label = QLabel("Summary will appear here after loading a file.")
        self.motec_summary_label.setStyleSheet("font-size: 16px;")

        layout.addWidget(self.motec_file_label)

        info_row = QHBoxLayout()

        summary_panel = QWidget()
        summary_layout = QVBoxLayout()

        summary_title = QLabel("MoTeC summary:")
        summary_title.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.motec_summary_label.setWordWrap(True)

        summary_layout.addWidget(summary_title)
        summary_layout.addWidget(self.motec_summary_label)
        summary_panel.setLayout(summary_layout)

        recommendation_panel = QWidget()
        recommendation_layout = QVBoxLayout()

        recommendation_title = QLabel("Suggested Scotch yoke dyno settings:")
        recommendation_title.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.motec_recommendation_box = QTextEdit()
        self.motec_recommendation_box.setReadOnly(True)
        self.motec_recommendation_box.setMinimumHeight(240)
        self.motec_recommendation_box.setMinimumWidth(500)
        self.motec_recommendation_box.setPlainText(
            "Dyno recommendations will appear here after loading a MoTeC file."
        )

        recommendation_layout.addWidget(recommendation_title)
        recommendation_layout.addWidget(self.motec_recommendation_box)
        recommendation_panel.setLayout(recommendation_layout)

        info_row.addWidget(summary_panel, 1)
        info_row.addWidget(recommendation_panel, 2)

        layout.addLayout(info_row)

        plot_grid = QGridLayout()

        self.motec_position_time_plot = pg.PlotWidget(title="Shock Position vs Time")
        self.motec_velocity_time_plot = pg.PlotWidget(title="Shock Velocity vs Time")

        self.motec_position_time_plot.setLabel("left", "Position", units="in")
        self.motec_position_time_plot.setLabel("bottom", "Time", units="s")

        self.motec_velocity_time_plot.setLabel("left", "Velocity", units="in/s")
        self.motec_velocity_time_plot.setLabel("bottom", "Time", units="s")

        self.motec_position_time_curve = self.motec_position_time_plot.plot()
        self.motec_velocity_time_curve = self.motec_velocity_time_plot.plot()

        plot_grid.addWidget(self.motec_position_time_plot, 0, 0)
        plot_grid.addWidget(self.motec_velocity_time_plot, 0, 1)

        layout.addLayout(plot_grid)

        page.setLayout(layout)
        return page


#-----------------Place holder tab Definition --------------------------------------
    def build_placeholder_tab(self, name: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout()

        label = QLabel(f"{name} page coming soon")
        label.setStyleSheet("font-size: 22px; font-weight: bold;")

        description = QLabel(
            "This tab is a placeholder for now. "
            "We are building the Live Test page first."
        )

        layout.addWidget(label)
        layout.addWidget(description)
        page.setLayout(layout)

        return page

    def build_help_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout()

        title = QLabel("RR Shock Dyno Help")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")

        help_text = QLabel(
            "Basic workflow:\n"
            "1. Select simulated data or connect Teensy.\n"
            "2. Enter test information.\n"
            "3. Select Scotch yoke stroke and motor RPM.\n"
            "4. Zero force and position.\n"
            "5. Start recording.\n"
            "6. Run the dyno.\n"
            "7. Stop recording.\n"
            "8. Save CSV.\n\n"
            "Safety note:\n"
            "Software can help enforce workflow, but physical safety must come from "
            "hardware E-stop, guards, limit switches, and proper mechanical design."
        )

        layout.addWidget(title)
        layout.addWidget(help_text)
        page.setLayout(layout)

        return page

    # ---------------------------------------------------------
    # GUI actions
    # ---------------------------------------------------------

    def start_simulation_mode(self):
        self.data_source.reset()
        self.clear_live_plots()

        if not self.update_timer.isActive():
            self.update_timer.start()

        self.status_label.setText("Status: Simulation mode active")

    def zero_force(self):
        QMessageBox.information(
            self,
            "Zero Force",
            "Prototype action: force zero would be saved here later."
        )

    def zero_position(self):
        QMessageBox.information(
            self,
            "Zero Position",
            "Prototype action: position zero would be saved here later."
        )

    def start_recording(self):
        self.recorded_samples = []
        self.clear_live_plots()
        self.test_start_time = time.time()
        self.is_recording = True

        if not self.update_timer.isActive():
            self.update_timer.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.save_button.setEnabled(False)

        self.status_label.setText("Status: Recording")

    def stop_recording(self):
        self.is_recording = False

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.save_button.setEnabled(True)

        self.status_label.setText("Status: Recording stopped")

    def save_recording_csv(self):
        if not self.recorded_samples:
            QMessageBox.warning(self, "No Data", "There are no samples to save.")
            return

        default_folder = self.project_root / "data" / "raw"
        default_folder.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_test_name = self.get_safe_test_name()
        default_path = default_folder / f"{timestamp}_{safe_test_name}_raw.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Raw Dyno CSV",
            str(default_path),
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        fieldnames = [
            "time_s",
            "force_lbf",
            "position_in",
            "velocity_in_s",
            "stroke_setting_in",
            "motor_rpm",
            "corner",
            "test_name",
            "operator",
            "notes",
        ]

        try:
            # Save raw CSV
            with open(file_path, mode="w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.recorded_samples)

            # Create processed CSV
            processed_df = process_raw_samples(self.recorded_samples)
            summary = summarize_processed_data(processed_df)

            processed_folder = self.project_root / "data" / "processed"
            processed_folder.mkdir(parents=True, exist_ok=True)

            raw_path = Path(file_path)
            processed_path = processed_folder / raw_path.name.replace(
                "_raw.csv",
                "_processed.csv"
            )

            processed_df.to_csv(processed_path, index=False)

            # Create plot PNG files
            plots_folder = self.project_root / "data" / "plots"
            plot_base_name = raw_path.stem.replace("_raw", "")

            plot_paths = save_standard_dyno_plots(
                df=processed_df,
                plots_folder=plots_folder,
                base_name=plot_base_name,
            )

            QMessageBox.information(
                self,
                "Test Saved",
                "Saved raw data, processed data, and plot images.\n\n"
                f"Raw CSV:\n{file_path}\n\n"
                f"Processed CSV:\n{processed_path}\n\n"
                f"Force vs Position Plot:\n{plot_paths['force_position']}\n\n"
                f"Force vs Velocity Plot:\n{plot_paths['force_velocity']}\n\n"
                f"Samples: {summary['sample_count']}\n"
                f"Duration: {summary['duration_s']:.2f} s\n"
                f"Peak force: {summary['peak_force_lbf']:.1f} lbf\n"
                f"Min force: {summary['min_force_lbf']:.1f} lbf\n"
                f"Peak velocity: {summary['peak_velocity_in_s']:.2f} in/s\n"
                f"Min velocity: {summary['min_velocity_in_s']:.2f} in/s"
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Could not save test data:\n\n{error}"
            )

    def open_motec_csv(self):
        default_folder = self.project_root / "data" / "imported_samples"
        default_folder.mkdir(parents=True, exist_ok=True)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open MoTeC Shock CSV",
            str(default_folder),
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        try:
            df = load_motec_shock_csv(file_path)

            self.imported_motec_df = df
            self.imported_motec_path = Path(file_path)

            self.update_motec_import_display(df)

            self.save_motec_processed_button.setEnabled(True)

        except Exception as error:
            QMessageBox.critical(
                self,
                "MoTeC Import Error",
                f"Could not import MoTeC CSV:\n\n{error}"
            )

    def update_motec_import_display(self, df: pd.DataFrame):
        summary = summarize_motec_shock_data(df)

        source_column = df.attrs.get("source_position_column", "Unknown")
        source_units = df.attrs.get("source_position_units", "Unknown")

        self.motec_file_label.setText(
            f"Loaded: {self.imported_motec_path}\n"
            f"Position channel: {source_column} ({source_units})"
        )

        self.motec_summary_label.setText(
            f"Samples: {summary['sample_count']}\n"
            f"Duration: {summary['duration_s']:.2f} s\n"
            f"Min position: {summary['min_position_in']:.3f} in\n"
            f"Max position: {summary['max_position_in']:.3f} in\n"
            f"Observed travel used: {summary['travel_used_in']:.3f} in\n"
            f"Max positive velocity: {summary['max_positive_velocity_in_s']:.2f} in/s\n"
            f"Max negative velocity: {summary['max_negative_velocity_in_s']:.2f} in/s"
        )
        recommendations = recommend_scotch_yoke_settings(df)

        recommendation_lines = []
        recommendation_lines.append("Velocity targets from moving shock data:")
        recommendation_lines.append(
            f"Motion filter: |velocity| >= "
            f"{recommendations['minimum_motion_velocity_in_s']:.1f} in/s"
        )
        recommendation_lines.append(
            f"Moving samples: {recommendations['motion_sample_count']} / "
            f"{recommendations['total_sample_count']} "
            f"({recommendations['motion_percent']:.1f}%)"
        )
        recommendation_lines.append("")

        for target_name, target_velocity in recommendations["velocity_targets"].items():
            recommendation_lines.append(
                f"{target_name}: {target_velocity:.2f} in/s"
            )

        recommendation_lines.append("")
        recommendation_lines.append("Suggested motor RPM by stroke:")
        recommendation_lines.append("")

        preferred_strokes = [2.0, 4.0, 6.0, 8.0, 10.0]

        for target_name, target_velocity in recommendations["velocity_targets"].items():
            recommendation_lines.append(f"{target_name}:")

            for stroke_in in preferred_strokes:
                rpm = 0.0

                for row in recommendations["rpm_recommendations"]:
                    if (
                            row["target_name"] == target_name
                            and row["stroke_in"] == stroke_in
                    ):
                        rpm = row["rpm"]
                        break

                recommendation_lines.append(
                    f"  {stroke_in:.0f} in stroke: {rpm:.1f} RPM"
                )

            recommendation_lines.append("")

        recommendation_lines.append(
            "Note: peak observed velocity may include noise/spikes. "
            "The 99% and 99.5% targets are usually better starting points."
        )

        self.motec_recommendation_box.setPlainText(
            "\n".join(recommendation_lines)
        )

        display_df = df

        max_display_points = 5000

        if len(display_df) > max_display_points:
            step = max(1, len(display_df) // max_display_points)
            display_df = display_df.iloc[::step]

        self.motec_position_time_curve.setData(
            display_df["time_s"].to_numpy(),
            display_df["shock_position_in"].to_numpy(),
        )

        self.motec_velocity_time_curve.setData(
            display_df["time_s"].to_numpy(),
            display_df["shock_velocity_in_s"].to_numpy(),
        )

    def save_motec_processed_csv(self):
        if self.imported_motec_df is None or self.imported_motec_path is None:
            QMessageBox.warning(
                self,
                "No MoTeC Data",
                "Open a MoTeC CSV before saving."
            )
            return

        output_folder = self.project_root / "data" / "motec_processed"
        output_folder.mkdir(parents=True, exist_ok=True)

        default_path = output_folder / f"{self.imported_motec_path.stem}_motec_processed.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Imported MoTeC Data",
            str(default_path),
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        try:
            self.imported_motec_df.to_csv(file_path, index=False)

            QMessageBox.information(
                self,
                "MoTeC Data Saved",
                f"Imported MoTeC data saved to:\n{file_path}"
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Could not save imported MoTeC data:\n\n{error}"
            )

    def clear_motec_import_display(self):
        self.imported_motec_df = None
        self.imported_motec_path = None

        self.motec_position_time_curve.setData([], [])
        self.motec_velocity_time_curve.setData([], [])

        self.motec_file_label.setText("No MoTeC CSV loaded")
        self.motec_summary_label.setText("Summary will appear here after loading a file.")

        self.save_motec_processed_button.setEnabled(False)

        self.motec_recommendation_box.setPlainText(
            "Dyno recommendations will appear here after loading a MoTeC file."
        )


    # ---------------------------------------------------------
    # Live data / simulation
    # ---------------------------------------------------------

    def update_live_data(self):
        sample = self.data_source.get_sample(
            stroke_in=self.get_stroke_setting(),
            rpm=self.get_motor_rpm(),
            test_start_time=self.test_start_time,
        )

        full_sample = self.add_test_metadata(sample)

        self.force_label.setText(f"Force: {full_sample['force_lbf']:.1f} lbf")
        self.position_label.setText(f"Position: {full_sample['position_in']:.3f} in")
        self.velocity_label.setText(f"Velocity: {full_sample['velocity_in_s']:.2f} in/s")

        self.update_live_plots(full_sample)

        if self.is_recording:
            self.recorded_samples.append(full_sample)

        self.sample_count_label.setText(
            f"Samples recorded: {len(self.recorded_samples)}"
        )

    def update_live_plots(self, sample: dict):
        self.plot_time.append(sample["time_s"])
        self.plot_force.append(sample["force_lbf"])
        self.plot_position.append(sample["position_in"])
        self.plot_velocity.append(sample["velocity_in_s"])

        if len(self.plot_time) > self.max_plot_points:
            self.plot_time = self.plot_time[-self.max_plot_points:]
            self.plot_force = self.plot_force[-self.max_plot_points:]
            self.plot_position = self.plot_position[-self.max_plot_points:]
            self.plot_velocity = self.plot_velocity[-self.max_plot_points:]

        self.force_time_curve.setData(self.plot_time, self.plot_force)
        self.position_time_curve.setData(self.plot_time, self.plot_position)
        self.force_position_curve.setData(self.plot_position, self.plot_force)
        self.force_velocity_curve.setData(self.plot_velocity, self.plot_force)

    def clear_live_plots(self):
        self.plot_time = []
        self.plot_force = []
        self.plot_position = []
        self.plot_velocity = []

        self.force_time_curve.setData([], [])
        self.position_time_curve.setData([], [])
        self.force_position_curve.setData([], [])
        self.force_velocity_curve.setData([], [])

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def add_test_metadata(self, sample: dict) -> dict:
        full_sample = sample.copy()

        full_sample.update(
            {
                "stroke_setting_in": self.get_stroke_setting(),
                "motor_rpm": self.get_motor_rpm(),
                "corner": self.corner_input.currentText(),
                "test_name": self.test_name_input.text().strip(),
                "operator": self.operator_input.text().strip(),
                "notes": self.notes_box.toPlainText().strip(),
            }
        )

        return full_sample

    def update_expected_velocity(self):
        stroke_in = self.get_stroke_setting()
        rpm = self.get_motor_rpm()

        crank_radius_in = stroke_in / 2.0
        frequency_hz = rpm / 60.0
        omega = 2.0 * math.pi * frequency_hz
        peak_velocity = crank_radius_in * omega

        self.expected_velocity_label.setText(
            f"Expected peak velocity: {peak_velocity:.2f} in/s"
        )

    def get_stroke_setting(self) -> float:
        try:
            return float(self.stroke_combo.currentText())
        except ValueError:
            return 4.0

    def get_motor_rpm(self) -> float:
        try:
            return float(self.rpm_input.text())
        except ValueError:
            return 0.0

    def get_safe_test_name(self) -> str:
        name = self.test_name_input.text().strip()

        if not name:
            name = "shock_test"

        safe_name = ""
        for char in name:
            if char.isalnum() or char in ("-", "_"):
                safe_name += char
            elif char.isspace():
                safe_name += "_"

        return safe_name or "shock_test"

    def open_processed_csv(self):
        default_folder = self.project_root / "data" / "processed"
        default_folder.mkdir(parents=True, exist_ok=True)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Processed Dyno CSV",
            str(default_folder),
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        try:
            df = pd.read_csv(file_path)

            required_columns = [
                "time_s",
                "force_lbf",
                "position_in",
                "calculated_velocity_in_s",
            ]

            missing_columns = [
                column for column in required_columns
                if column not in df.columns
            ]

            if missing_columns:
                QMessageBox.warning(
                    self,
                    "Invalid Processed CSV",
                    "This file is missing required columns:\n\n"
                    + "\n".join(missing_columns)
                )
                return

            self.analysis_file_label.setText(f"Loaded: {file_path}")
            self.update_analysis_plots(df)

        except Exception as error:
            QMessageBox.critical(
                self,
                "Open Error",
                f"Could not open processed CSV:\n\n{error}"
            )

    def update_analysis_plots(self, df: pd.DataFrame):
        self.analysis_force_position_curve.setData(
            df["position_in"].to_numpy(),
            df["force_lbf"].to_numpy(),
        )

        self.analysis_force_velocity_curve.setData(
            df["calculated_velocity_in_s"].to_numpy(),
            df["force_lbf"].to_numpy(),
        )

        sample_count = len(df)
        duration_s = df["time_s"].max() - df["time_s"].min()
        peak_force = df["force_lbf"].max()
        min_force = df["force_lbf"].min()
        peak_velocity = df["calculated_velocity_in_s"].max()
        min_velocity = df["calculated_velocity_in_s"].min()

        self.analysis_summary_label.setText(
            f"Samples: {sample_count}\n"
            f"Duration: {duration_s:.2f} s\n"
            f"Peak force: {peak_force:.1f} lbf\n"
            f"Min force: {min_force:.1f} lbf\n"
            f"Peak velocity: {peak_velocity:.2f} in/s\n"
            f"Min velocity: {min_velocity:.2f} in/s"
        )

    def clear_analysis_plots(self):
        self.analysis_force_position_curve.setData([], [])
        self.analysis_force_velocity_curve.setData([], [])

        self.analysis_file_label.setText("No processed CSV loaded")
        self.analysis_summary_label.setText("Summary will appear here after loading a test.")

    def build_calibration_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Sensor Calibration")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")

        subtitle = QLabel(
            "Edit sensor calibration values. Later, this page will guide users through zeroing and known-load calibration."
        )
        subtitle.setStyleSheet("font-size: 14px; color: gray;")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()

        self.force_zero_input = QLineEdit()
        self.force_scale_input = QLineEdit()
        self.position_zero_input = QLineEdit()
        self.position_scale_input = QLineEdit()

        form.addRow("Force zero raw:", self.force_zero_input)
        form.addRow("Force scale, lbf per raw count:", self.force_scale_input)
        form.addRow("Position zero raw:", self.position_zero_input)
        form.addRow("Position scale, inches per raw count:", self.position_scale_input)

        layout.addLayout(form)

        button_row = QHBoxLayout()

        self.load_calibration_button = QPushButton("Reload Calibration")
        self.save_calibration_button = QPushButton("Save Calibration")

        self.load_calibration_button.clicked.connect(self.reload_calibration_fields)
        self.save_calibration_button.clicked.connect(self.save_calibration_from_fields)

        button_row.addWidget(self.load_calibration_button)
        button_row.addWidget(self.save_calibration_button)

        layout.addLayout(button_row)

        help_text = QLabel(
            "Current simple formula:\n"
            "force_lbf = (force_raw - force_zero_raw) × force_scale\n"
            "position_in = (position_raw - position_zero_raw) × position_scale\n\n"
            "For now, these values are manually entered. Once the Teensy is connected, "
            "the Zero Force and Zero Position buttons can automatically fill in the zero values."
        )
        help_text.setStyleSheet("font-size: 14px;")

        layout.addWidget(help_text)

        page.setLayout(layout)

        self.reload_calibration_fields()

        return page

    def reload_calibration_fields(self):
        self.sensor_calibration = load_calibration(self.calibration_path)

        self.force_zero_input.setText(
            str(self.sensor_calibration["force"]["zero_raw"])
        )
        self.force_scale_input.setText(
            str(self.sensor_calibration["force"]["scale_lbf_per_raw"])
        )
        self.position_zero_input.setText(
            str(self.sensor_calibration["position"]["zero_raw"])
        )
        self.position_scale_input.setText(
            str(self.sensor_calibration["position"]["scale_in_per_raw"])
        )

        self.status_label.setText("Status: Calibration loaded")

    def save_calibration_from_fields(self):
        try:
            new_calibration = {
                "force": {
                    "zero_raw": float(self.force_zero_input.text()),
                    "scale_lbf_per_raw": float(self.force_scale_input.text()),
                },
                "position": {
                    "zero_raw": float(self.position_zero_input.text()),
                    "scale_in_per_raw": float(self.position_scale_input.text()),
                },
            }

            save_calibration(self.calibration_path, new_calibration)
            self.sensor_calibration = new_calibration

            QMessageBox.information(
                self,
                "Calibration Saved",
                f"Calibration saved to:\n{self.calibration_path}"
            )

            self.status_label.setText("Status: Calibration saved")

        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Calibration",
                "Calibration values must be valid numbers."
            )