"""Fetch a pinned official upstream release; no third-party download mirrors."""
import hashlib
from pathlib import Path
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip'
SHA256 = 'abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d'
FILES = ['realesrgan-ncnn-vulkan.exe', 'vcomp140.dll',
         'models/realesrgan-x4plus.bin', 'models/realesrgan-x4plus.param',
         'models/realesrgan-x4plus-anime.bin', 'models/realesrgan-x4plus-anime.param']


def download(url, target, expected=None):
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'WallpaperCoverSR/0.1'})
            with urllib.request.urlopen(request, timeout=30) as response, target.open('wb') as out:
                size = int(response.headers.get('Content-Length', 0))
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 100 * 1024 * 1024:
                        raise ValueError('Unexpected download size')
                    out.write(chunk)
            if size and size != total:
                raise ValueError('Incomplete download')
            if expected and hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError('SHA256 mismatch')
            return
        except Exception:
            target.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(2)


def main():
    vendor = ROOT / 'vendor'
    vendor.mkdir(exist_ok=True)
    archive = vendor / 'realesrgan-official.zip'
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        print('Downloading official Real-ESRGAN release (~43 MiB)...', flush=True)
        download(URL, archive, SHA256)
    dest = vendor / 'realesrgan'
    with zipfile.ZipFile(archive) as package:
        for name in FILES:
            path = dest / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(package.read(name))
    licenses = vendor / 'licenses'
    licenses.mkdir(exist_ok=True)
    for name, url in {
        'Real-ESRGAN-LICENSE.txt': 'https://raw.githubusercontent.com/xinntao/Real-ESRGAN/master/LICENSE',
        'Real-ESRGAN-ncnn-LICENSE.txt': 'https://raw.githubusercontent.com/xinntao/Real-ESRGAN-ncnn-vulkan/master/LICENSE',
        'ncnn-LICENSE.txt': 'https://raw.githubusercontent.com/Tencent/ncnn/master/LICENSE.txt',
        'libwebp-COPYING.txt': 'https://raw.githubusercontent.com/webmproject/libwebp/main/COPYING',
    }.items():
        download(url, licenses / name)
    print('Backend ready; archive SHA256 verified.')


if __name__ == '__main__':
    main()
