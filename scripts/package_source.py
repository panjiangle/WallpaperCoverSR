"""Create a shareable source archive using an explicit allow-list."""
import hashlib
from pathlib import Path
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wallpaper_cover_sr import __version__
ITEMS = ['wallpaper_cover_sr', 'scripts', 'tests', '.github', 'site', 'docs/technical.md', 'run.py',
         'requirements.txt', '.gitignore', 'README.md', 'CHANGELOG.md', 'LICENSE',
         'THIRD_PARTY_NOTICES.md', 'VALIDATION.md', '使用说明.txt']


def package_source():
    dest = ROOT / 'release' / f'WallpaperCoverSR-{__version__}-source.zip'
    dest.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ITEMS:
            path = ROOT / name
            files = path.rglob('*') if path.is_dir() else [path]
            for item in files:
                if item.is_file() and '__pycache__' not in item.parts and item.suffix != '.pyc':
                    archive.write(item, Path('WallpaperCoverSR') / item.relative_to(ROOT))
    dest.with_suffix('.zip.sha256').write_text(hashlib.sha256(dest.read_bytes()).hexdigest() + '  ' + dest.name + '\n', 'ascii')
    print(f'Source: {dest} ({dest.stat().st_size / 1024:.1f} KiB)')
    return dest


if __name__ == '__main__':
    package_source()
