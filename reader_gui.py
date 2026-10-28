"""Standalone screenshot reader. No emulator input or resource spending."""
import json
import sys
from dataclasses import asdict
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QFileDialog, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from lib.screen_reader import ScreenReader


class ReadTask(QThread):
    finished_text = pyqtSignal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            result = ScreenReader().read(self.path)
            self.finished_text.emit(json.dumps(asdict(result), indent=2))
        except Exception as error:
            self.finished_text.emit("Could not read screenshot: " + str(error))


class ReaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.task = None
        self.setWindowTitle("MFF Screenshot Reader")
        self.resize(760, 560)
        body = QWidget()
        layout = QVBoxLayout(body)
        label = QLabel("Open a screenshot of MFF at 1280 × 720, or the full 1312 × 753 BlueStacks window.\n"
                       "This reader does not click, battle, upgrade, or spend anything.")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.open_button = QPushButton("Open screenshot…")
        self.open_button.clicked.connect(self.choose)
        layout.addWidget(self.open_button)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlainText("Choose a screenshot. Example screenshots are in tests/fixtures.\n\n"
                                 "Recognized screens: World Event, GBR Onslaught rewards, Otherworld, "
                                 "Timeline and the arena status board.\n\n"
                                 "Battle controls are shelved. This window reads saved images only.")
        layout.addWidget(self.output)
        self.setCentralWidget(body)

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open MFF screenshot", "", "Images (*.png *.jpg *.jpeg)")
        if not path:
            return
        self.open_button.setEnabled(False)
        self.output.setPlainText("Reading screenshot locally…")
        self.task = ReadTask(path)
        self.task.finished_text.connect(self.show_result)
        self.task.start()

    def show_result(self, text):
        self.output.setPlainText(text)
        self.open_button.setEnabled(True)

    def closeEvent(self, event):
        if self.task and self.task.isRunning():
            self.output.setPlainText("Wait for the current screenshot to finish reading before closing.")
            event.ignore()
        else:
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ReaderWindow()
    window.show()
    raise SystemExit(app.exec_())
