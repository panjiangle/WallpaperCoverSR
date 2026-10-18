from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wallpaper_cover_sr.app import tray_image
folder = Path(__file__).resolve().parents[1] / 'build'
folder.mkdir(exist_ok=True)
tray_image().save(folder / 'app.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
