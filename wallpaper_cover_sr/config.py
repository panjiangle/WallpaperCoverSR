"""User-local settings. No paths or private artwork belong in the source tree."""
from pathlib import Path
import json
import os
import sys
import threading
import winreg
from .files import replace_file

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
DATA = Path(os.environ['LOCALAPPDATA']) / 'WallpaperCoverSR'
DATA.mkdir(parents=True, exist_ok=True)
CACHE = DATA / 'cache'
CACHE.mkdir(exist_ok=True)
CONFIG = DATA / 'config.json'
DEFAULTS = {'enabled': True, 'scale': 4, 'model': 'realesrgan-x4plus',
            'cache_mb': 128, 'source_app': '', 'prefer_hd': True, 'netease_playlist': ''}


class Settings:
    def __init__(self):
        self.lock = threading.RLock()
        self.values = dict(DEFAULTS)
        if CONFIG.exists():
            saved = json.loads(CONFIG.read_text('utf-8'))
            self.values.update({k: v for k, v in saved.items() if k in DEFAULTS})
        if self.values['scale'] not in (2, 3, 4):
            self.values['scale'] = 4

    def get(self):
        with self.lock:
            return dict(self.values)

    def save(self, **changes):
        with self.lock:
            self.values.update(changes)
            tmp = CONFIG.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.values, ensure_ascii=False, indent=2), 'utf-8')
            replace_file(tmp, CONFIG)


RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, 'WallpaperCoverSR')
        return True
    except FileNotFoundError:
        return False


def set_startup(enabled):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            if getattr(sys, 'frozen', False):
                command = f'"{sys.executable}" --background'
            else:
                command = f'"{Path(sys.executable).with_name("pythonw.exe")}" "{ROOT / "run.py"}" --background'
            winreg.SetValueEx(key, 'WallpaperCoverSR', 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, 'WallpaperCoverSR')
            except FileNotFoundError:
                pass
