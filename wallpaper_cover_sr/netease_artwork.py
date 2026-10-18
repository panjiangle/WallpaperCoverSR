"""Read-only NetEase queue lookup and verified official-CDN artwork.

No account credentials, search APIs, client injection or background polling.
Only called when the real player's song/cover changes (or a bounded retry).
"""
import hashlib
import http.client
from io import BytesIO
import json
import logging
import math
import os
from pathlib import Path
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageChops, ImageOps, ImageStat

from .backend import Cancelled
from .config import CACHE
from .files import replace_file

LOG = logging.getLogger(__name__)
MAX_BYTES = 16 * 1024 * 1024
MAX_PIXELS = 4096 * 4096
DISPLAY_SIDE = 1024


class Unavailable(Exception):
    pass


def normalize(value):
    return ''.join(unicodedata.normalize('NFKC', value).casefold().split())


def cdn_url(value):
    """Upgrade known public image hosts; reject credentials, ports and redirects elsewhere."""
    parts = urllib.parse.urlsplit(value)
    if (parts.scheme not in ('http', 'https') or parts.username or parts.password
            or parts.port is not None
            or not re.fullmatch(r'p\d{1,2}\.music\.126\.net', parts.hostname or '')
            or not parts.path.startswith('/') or parts.path.startswith('//')):
        raise Unavailable('封面地址不在允许的网易云图片域名中')
    return urllib.parse.urlunsplit(('https', parts.hostname, parts.path, '', ''))


class CDNRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, cdn_url(newurl))


def candidates(info, playlist):
    if not info.get('title') or not info.get('artist'):
        raise Unavailable('歌曲名称或歌手不完整')
    title, artist = normalize(info['title']), normalize(info['artist'])
    album_name = normalize(info.get('album', ''))
    with Path(playlist).open('r', encoding='utf-8-sig') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise Unavailable('网易云播放队列过大')
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise Unavailable('无法识别网易云播放队列格式')
    listing = document.get('list')
    if not isinstance(listing, list) or len(listing) > 10000:
        raise Unavailable('无法识别网易云播放队列格式')
    found = {}
    for entry in listing:
        if not isinstance(entry, dict) or not isinstance(entry.get('track'), dict):
            continue
        track = entry['track']
        if not isinstance(track.get('name'), str) or normalize(track['name']) != title:
            continue
        people = track.get('artists', [])
        if not isinstance(people, list):
            continue
        names = [p['name'] for p in people if isinstance(p, dict) and isinstance(p.get('name'), str)]
        variants = {normalize(sep.join(names)) for sep in ('/', ',', '、', ';', '&', '，', ' feat. ')}
        # The desktop SMTC session may expose only the lead artist of a collaboration.
        if names:
            variants.add(normalize(names[0]))
        if not names or artist not in variants:
            continue
        album = track.get('album')
        if not isinstance(album, dict):
            continue
        if album_name and normalize(str(album.get('name', ''))) != album_name:
            continue
        try:
            url = cdn_url(album.get('picUrl', ''))
        except (Unavailable, ValueError, TypeError):
            continue
        found[url] = {'url': url, 'song_id': str(track.get('id', '')),
                      'album_id': str(album.get('id', ''))}
    if not found:
        raise Unavailable('本地队列中未找到对应高清封面')
    if len(found) > 4:
        raise Unavailable('同名歌曲版本过多，保留系统封面')
    return list(found.values())


def same_artwork(thumbnail, original):
    """Conservative color AND spatial-correlation check; blank images cannot verify identity."""
    a = thumbnail.resize((32, 32), Image.Resampling.LANCZOS).convert('RGB')
    b = original.resize((32, 32), Image.Resampling.LANCZOS).convert('RGB')
    mae = sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / (3 * 255)
    x, y = list(a.convert('L').get_flattened_data()), list(b.convert('L').get_flattened_data())
    mx, my = sum(x) / len(x), sum(y) / len(y)
    xx = sum((v - mx) ** 2 for v in x)
    yy = sum((v - my) ** 2 for v in y)
    if min(xx, yy) < len(x) * 16:
        return False
    correlation = sum((u - mx) * (v - my) for u, v in zip(x, y)) / math.sqrt(xx * yy)
    return mae <= 0.04 and correlation >= 0.97


def decode(data):
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > MAX_PIXELS or max(image.size) > 4096:
            raise Unavailable('封面尺寸超过处理上限')
        return ImageOps.exif_transpose(image).convert('RGB')


def fetch(url, cancelled, deadline):
    request = urllib.request.Request(cdn_url(url), headers={
        'User-Agent': 'WallpaperCoverSR/0.3', 'Referer': 'https://music.163.com/'})
    opener = urllib.request.build_opener(CDNRedirect())
    chunks, count = [], 0
    with opener.open(request, timeout=max(0.1, min(3, deadline - time.monotonic()))) as response:
        cdn_url(response.url)
        while True:
            if cancelled():
                raise Cancelled()
            if time.monotonic() >= deadline:
                raise Unavailable('高清封面获取超时')
            block = response.read(65536)
            if not block:
                break
            count += len(block)
            if count > MAX_BYTES:
                raise Unavailable('封面文件超过处理上限')
            chunks.append(block)
    return b''.join(chunks)


def resolve(info, settings, cancelled=lambda: False):
    """Return verified display artwork, or a short fallback reason. Cancellation propagates."""
    if not any(name in info.get('app', '').casefold() for name in ('cloudmusic', 'netease')):
        return None, ''
    started = time.perf_counter()
    deadline = time.monotonic() + 8
    playlist = settings.get('netease_playlist') or str(
        Path(os.environ['LOCALAPPDATA']) / 'NetEase/CloudMusic/webdata/file/playingList')
    try:
        if cancelled():
            raise Cancelled()
        matches = candidates(info, playlist)
        thumbnail = decode(info['data'])
        accepted = []
        for candidate in matches:
            if cancelled():
                raise Cancelled()
            if time.monotonic() >= deadline:
                raise Unavailable('高清封面获取超时')
            key = hashlib.sha256((candidate['url'] + '|hd-display-v1').encode()).hexdigest()
            output = CACHE / f'hd-{key}.png'
            meta = output.with_suffix('.json')
            hit = False
            try:
                if output.is_file() and meta.is_file():
                    image = decode(output.read_bytes())
                    original_size = json.loads(meta.read_text('utf-8'))['original_size']
                    if (len(original_size) != 2 or not all(isinstance(n, int) and 400 <= n <= 4096 for n in original_size)
                            or max(image.size) > DISPLAY_SIDE):
                        raise ValueError('Invalid cached artwork')
                    hit = True
            except (OSError, ValueError, KeyError, TypeError):
                hit = False
            if not hit:
                image = decode(fetch(candidate['url'], cancelled, deadline))
                original_size = list(image.size)
                if min(original_size) < 400:
                    continue
            if not same_artwork(thumbnail, image):
                continue
            if cancelled():
                raise Cancelled()
            if not hit:
                image.thumbnail((DISPLAY_SIDE, DISPLAY_SIDE), Image.Resampling.LANCZOS)
                temp = output.with_suffix('.tmp')
                try:
                    image.save(temp, format='PNG')
                    replace_file(temp, output)
                finally:
                    temp.unlink(missing_ok=True)
                temp_meta = meta.with_suffix('.tmp')
                try:
                    temp_meta.write_text(json.dumps({'original_size': original_size}), 'utf-8')
                    replace_file(temp_meta, meta)
                finally:
                    temp_meta.unlink(missing_ok=True)
            output.touch()
            accepted.append({'file': str(output), 'input': list(thumbnail.size),
                'original_size': original_size, 'output': list(image.size),
                'cache_hit': hit, 'seconds': round(time.perf_counter() - started, 3),
                'model': 'none', 'artwork_source': 'netease-original',
                'song_id': candidate['song_id'], 'album_id': candidate['album_id']})
        if len(accepted) == 1:
            return accepted[0], ''
        if len(accepted) > 1:
            raise Unavailable('多个版本封面相似，保留系统封面')
        raise Unavailable('未通过封面核对，保留系统封面')
    except Cancelled:
        raise
    except (Unavailable, OSError, ValueError, TypeError, KeyError,
            Image.DecompressionBombError, http.client.HTTPException, urllib.error.URLError) as exc:
        LOG.info('HD artwork unavailable (%s); using system artwork', type(exc).__name__)
        return None, str(exc) if isinstance(exc, Unavailable) else '高清原封面暂不可用'
