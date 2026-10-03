import sys
import pyqtgraph as pg
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox


from src.gui.main_window import MainWindow


APP_NAME = "RR Shock Dyno"


def get_project_root() -> Path:
    """
    Returns the main project folder.

    This lets the rest of the program find folders like:
    - config/
    - data/
    - docs/
    - sample_data/
    """
    return Path(__file__).resolve().parent


def main() -> int:
    project_root = get_project_root()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    try:
        window = MainWindow(project_root=project_root)
        window.show()

        return app.exec()

    except Exception as error:
        QMessageBox.critical(
            None,
            "Shock Dyno Startup Error",
            f"The program failed to start:\n\n{error}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())