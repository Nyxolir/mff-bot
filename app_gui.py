import lib.logger as logging
import os
import sys
import traceback
from PyQt5 import QtWidgets, QtCore


def main():
    from lib.gui.widgets.modern_main import ModernMainWindow
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    app = QtWidgets.QApplication(sys.argv)
    from pathlib import Path
    from PyQt5.QtGui import QIcon
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / 'icon.ico')))
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('MFFAuto.Farming.Desktop')
    window = ModernMainWindow()
    if '--self-test' in sys.argv:
        from lib.installer_selftest import run_self_test
        result=run_self_test(window,sys.argv[sys.argv.index('--self-test')+1])
        window.close()
        return result
    if '--trivia' in sys.argv:
        from datetime import datetime,timezone
        window.trivia_retry_at=datetime.now(timezone.utc)
    window.start_queue_after_connect='--start-queue' in sys.argv
    if '--minimized' in sys.argv:window.showMinimized()
    else:window.show()
    if '--connect' in sys.argv or window.start_queue_after_connect:
        QtCore.QTimer.singleShot(0,window.connect_emulator)
    return app.exec_()


def check_updates():
    import version
    return version.mff_auto, False


def create_updater_notification():
    from PyQt5.QtWidgets import QDialog
    from lib.gui.designes.updater_notification import Ui_Dialog
    from lib.gui.helper import set_default_icon
    notification = QDialog()
    Ui_Dialog().setupUi(Dialog=notification)
    set_default_icon(window=notification)
    return notification


def suppress_qt_warnings():
    from os import environ
    environ["QT_DEVICE_PIXEL_RATIO"] = "0"
    environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    environ["QT_SCREEN_SCALE_FACTORS"] = "1"
    environ["QT_SCALE_FACTOR"] = "1"


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    import multiprocess
    multiprocess.freeze_support()
    if '--self-test' in sys.argv:
        os.environ['QT_QPA_PLATFORM']='offscreen'
    suppress_qt_warnings()
    try:
        from lib.app_paths import prepare_runtime
        os.chdir(prepare_runtime())
        sys.exit(main())
    except Exception as err:
        logging.root.error(f"{err}\n{traceback.format_exc()}")
        if '--self-test' in sys.argv:
            import json
            from pathlib import Path
            report=Path(sys.argv[sys.argv.index('--self-test')+1])
            report.write_text(json.dumps({'passed':False,'error':str(err),'traceback':traceback.format_exc()},indent=2),encoding='utf-8')
            sys.exit(1)
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        QtWidgets.QMessageBox.critical(None,"MFF Auto could not start",str(err))
        sys.exit(1)
