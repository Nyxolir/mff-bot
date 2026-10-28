"""Separate immutable installed resources from per-user state; source runs stay in place."""
import os
from pathlib import Path
import sys


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def data_root():
    override = os.environ.get('MFF_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, 'frozen', False):
        local = os.environ.get('LOCALAPPDATA')
        if not local:
            raise RuntimeError('Windows LOCALAPPDATA is unavailable')
        return Path(local) / 'Nyxolir' / 'MFFBot'
    return resource_root()


def data_path(relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Application data paths must remain inside the data directory')
    return data_root() / path


def prepare_runtime():
    for relative in ('settings/gui', 'diagnostics', 'logs', '.cache/ocr'):
        data_path(relative).mkdir(parents=True, exist_ok=True)
    return data_root()
