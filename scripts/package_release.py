import hashlib
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.download_backend import FILES
from wallpaper_cover_sr import __version__

dest = ROOT / 'dist' / 'WallpaperCoverSR'
for name in FILES:
    target = dest / 'vendor' / 'realesrgan' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'vendor' / 'realesrgan' / name, target)
shutil.copytree(ROOT / 'vendor' / 'licenses', dest / 'licenses' / 'backend', dirs_exist_ok=True)
for name in ['README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', '使用说明.txt', 'VALIDATION.md']:
    shutil.copy2(ROOT / name, dest / name)
shutil.copytree(ROOT / 'site', dest / 'site', dirs_exist_ok=True)
(dest / 'docs').mkdir(exist_ok=True)
shutil.copy2(ROOT / 'docs' / 'technical.md', dest / 'docs' / 'technical.md')
# Include licenses bundled with Python packages by their upstream distributions.
for parent in [ROOT / '.venv' / 'Lib' / 'site-packages']:
    if parent.exists():
        for pkg in parent.glob('*.dist-info'):
            license_dir = pkg / 'licenses'
            if license_dir.exists():
                shutil.copytree(license_dir, dest / 'licenses' / pkg.name, dirs_exist_ok=True)
release = ROOT / 'release'
release.mkdir(exist_ok=True)
archive = Path(shutil.make_archive(str(release / f'WallpaperCoverSR-{__version__}-windows-x64'), 'zip', ROOT / 'dist', 'WallpaperCoverSR'))
(release / (archive.name + '.sha256')).write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', 'ascii')
print(f'{archive} ({archive.stat().st_size / 1024**2:.1f} MiB)')
from scripts.package_source import package_source
package_source()
