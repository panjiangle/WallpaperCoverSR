"""Invoke the upstream executable once per new cover. No ML runtime stays loaded."""
from io import BytesIO
import hashlib
import json
from pathlib import Path
import subprocess
import time

from PIL import Image

from .config import ROOT, DATA, CACHE
from .integration import NO_WINDOW
from .files import replace_file


class Cancelled(Exception):
    pass


def process(data, settings, cancelled=lambda: False):
    model = settings['model']
    if model not in ('realesrgan-x4plus', 'realesrgan-x4plus-anime'):
        raise ValueError('不支持的模型')
    scale = settings['scale']
    if scale not in (2, 3, 4):
        raise ValueError('倍率必须是 2、3 或 4')
    digest = hashlib.sha256(data + model.encode() + b'official-20220424-v1').hexdigest()
    output = CACHE / f'{digest}-x{scale}.png'
    base = CACHE / f'{digest}-x4.png'
    image = Image.open(BytesIO(data))
    width, height = image.size
    if width * height > 4096 * 4096:
        raise ValueError('封面尺寸异常')
    image.load()
    started = time.perf_counter()
    hit = output.is_file()
    if not hit:
        if max(width, height) >= 512:
            image.convert('RGB').save(output)
        else:
            if not base.is_file():
                upstream = ROOT / 'vendor' / 'realesrgan'
                exe = upstream / 'realesrgan-ncnn-vulkan.exe'
                if not exe.is_file():
                    raise RuntimeError('未找到 Real-ESRGAN。请运行 scripts/download_backend.py 或使用完整便携包。')
                source = CACHE / f'{digest}-input.png'
                temp = CACHE / f'{digest}-working.png'
                image.convert('RGB').save(source)
                args = [str(exe), '-i', str(source), '-o', str(temp), '-m', str(upstream / 'models'),
                        '-n', model, '-s', '4', '-t', '128', '-j', '1:1:1', '-f', 'png']
                try:
                    # Child exits after inference, releasing GPU memory immediately.
                    with (DATA / 'backend.log').open('w', encoding='utf-8') as log:
                        child = subprocess.Popen(args, stdout=log, stderr=log, creationflags=NO_WINDOW)
                        try:
                            deadline = time.monotonic() + 120
                            while child.poll() is None:
                                if cancelled():
                                    raise Cancelled()
                                if time.monotonic() > deadline:
                                    raise TimeoutError('超分超过 120 秒，请查看 backend.log 或更新显卡驱动')
                                time.sleep(0.15)
                            if child.returncode:
                                raise RuntimeError(f'Real-ESRGAN 退出码 {child.returncode}，详见 backend.log')
                        finally:
                            if child.poll() is None:
                                child.terminate()
                                try:
                                    child.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    child.kill()
                                    child.wait(timeout=5)
                    with Image.open(temp) as result:
                        if result.size != (width * 4, height * 4):
                            raise ValueError('Real-ESRGAN 输出尺寸异常')
                        result.verify()
                    replace_file(temp, base)
                finally:
                    source.unlink(missing_ok=True)
                    temp.unlink(missing_ok=True)
            if scale != 4:
                with Image.open(base) as result:
                    result.resize((width * scale, height * scale), Image.Resampling.LANCZOS).save(output)
    if cancelled():
        raise Cancelled()
    output.touch()
    with Image.open(output) as result:
        result_size = list(result.size)
    return {'file': str(output), 'input': [width, height], 'output': result_size,
            'cache_hit': hit, 'seconds': round(time.perf_counter() - started, 3), 'model': model}


def trim_cache(limit_mb, keep):
    files = sorted(CACHE.glob('*.png'), key=lambda p: p.stat().st_mtime, reverse=True)
    total = 0
    for path in files:
        total += path.stat().st_size
        if total > limit_mb * 1024 * 1024 and str(path) not in keep:
            path.unlink(missing_ok=True)
            if path.name.startswith('hd-'):
                path.with_suffix('.json').unlink(missing_ok=True)
