"""Start the desktop app without keeping a console window open."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
child = subprocess.Popen([sys.executable,str(root / "app_gui.py")],cwd=root,
    creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
if "--wait" in sys.argv:
    raise SystemExit(child.wait())
