"""Application entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox

from launcher.window import LauncherWindow


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def configure_ui_font(app: QApplication) -> None:
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc"
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 9))
            return
    app.setFont(QFont("Segoe UI", 9))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-autostart", action="store_true")
    arguments = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("FeinaLive Control Center")
    app.setOrganizationName("feinaLive")
    configure_ui_font(app)
    lock_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)) / "feinalive-launcher.lock"
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(0)
    if not lock.tryLock(50):
        QMessageBox.information(None, "FeinaLive", "控制中心已经在运行。")
        return 0

    window = LauncherWindow(project_root(), autostart=not arguments.no_autostart)
    window.show()
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
