"""Opt-in Windows/Wallpaper Engine integration checks (not run in CI).

Default: exercise the real worker's 2x/3x/4x output and disabled/exit fallback.
--external-helper: validate the already-running portable application instead.
--case PROJECT LEFT TOP RIGHT BOTTOM: also verify the original wallpaper's
rendered cover using a temporary green media thumbnail. Repeat for any number
of wallpapers. Coordinates are inside a 1280x760 preview window.
"""
import argparse
import asyncio
import ctypes
from ctypes import wintypes as w
import hashlib
from io import BytesIO
from pathlib import Path
import sys
import time

from PIL import Image, ImageGrab, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wallpaper_cover_sr.config import DATA, Settings
from wallpaper_cover_sr import integration
from wallpaper_cover_sr.media_bridge import MediaBridge
from wallpaper_cover_sr.media_policy import choose_source, is_own_session
from wallpaper_cover_sr.worker import Manager, Worker, read_cover, source_snapshot


async def until(predicate, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        await asyncio.sleep(0.05)
    raise AssertionError('Timed out waiting for enhanced Windows media session/output')


async def real_source(manager):
    sessions, descriptions, current = source_snapshot(manager)
    app_id = choose_source(descriptions, current)
    if app_id is None:
        raise RuntimeError('Start a media player with artwork first.')
    return sessions[app_id]


async def check_published(manager, expected):
    await until(lambda: manager.get_current_session() and is_own_session(manager.get_current_session().source_app_user_model_id))
    info = await read_cover(manager.get_current_session())
    assert info, 'Enhancement session has no artwork'
    with Image.open(BytesIO(info['data'])) as image:
        assert list(image.size) == expected, (image.size, expected)
    return info


async def check_worker(manager, external, require_hd=False):
    import json
    settings = Settings()
    original = settings.get()
    service = None
    if external:
        try:
            status = json.loads((DATA / 'status.json').read_text('utf-8'))
            assert status.get('mode') == 'windows-media-bridge', 'This is not the universal media bridge'
            proxy = await check_published(manager, status['output'])
            assert hashlib.sha256(proxy['data']).digest() == hashlib.sha256(Path(status['file']).read_bytes()).digest()
            source = await real_source(manager)
            original_info = await read_cover(source)
            assert proxy['title'] == original_info['title'] and proxy['artist'] == original_info['artist']
            if require_hd:
                assert status.get('artwork_source') == 'netease-original' and status.get('model') == 'none'
                assert max(status['output']) <= 1024
            print('PASS: portable application publishes its full processed PNG through Windows SMTC', flush=True)
            return
        except AssertionError as exc:
            raise AssertionError('Universal output is unavailable: ' + str(exc)) from exc
    assert not any(is_own_session(s.source_app_user_model_id) for s in manager.get_sessions()), 'Exit the app before running this test.'
    try:
        settings.save(enabled=True, scale=4, prefer_hd=False)
        service = Worker(settings)
        service.thread.start()
        for scale in (2, 3, 4):
            source = await real_source(manager)
            source_info = await read_cover(source)
            with Image.open(BytesIO(source_info['data'])) as image:
                expected = [n * scale for n in image.size] if max(image.size) < 512 else list(image.size)
            settings.save(scale=scale)
            service.poke()
            await until(lambda: service.get_info().get('state') == 'ready' and service.get_info().get('output') == expected)
            published = await check_published(manager, expected)
            assert published['title'] == source_info['title'] and published['artist'] == source_info['artist']
            print(f'PASS: {scale}x full artwork {expected}, title and artist', flush=True)
        settings.save(enabled=False)
        service.poke()
        await until(lambda: service.get_info().get('state') == 'disabled')
        await until(lambda: not any(is_own_session(s.source_app_user_model_id) for s in manager.get_sessions()))
        print('PASS: disabled removes the enhancement session and restores real player', flush=True)
    finally:
        if service:
            service.stop()
            await asyncio.to_thread(service.thread.join, 10)
            assert not service.thread.is_alive(), 'Worker did not stop'
        settings.save(**original)
    await until(lambda: not any(is_own_session(s.source_app_user_model_id) for s in manager.get_sessions()))
    print('PASS: exit leaves no enhancement session behind', flush=True)


async def check_wallpapers(manager, cases):
    if not cases:
        return
    assert not any(is_own_session(s.source_app_user_model_id) for s in manager.get_sessions()), 'Exit the application before renderer checks.'
    engine = integration.find_engine()
    source = await real_source(manager)
    bridge = MediaBridge(asyncio.get_running_loop())
    u = ctypes.windll.user32
    u.SetProcessDPIAware()
    u.GetForegroundWindow.restype = w.HWND
    u.FindWindowW.restype = w.HWND
    u.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
    u.IsZoomed.argtypes = [w.HWND]
    u.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT]
    foreground = u.GetForegroundWindow()
    was_maximized = u.IsZoomed(foreground)
    name = 'CoverSR-Universal-Verification'
    color = (20, 220, 60)
    stream = BytesIO()
    Image.new('RGB', (540, 540), color).save(stream, 'PNG')
    artwork = stream.getvalue()
    u.ShowWindow(foreground, 6)
    try:
        for project, left, top, right, bottom in cases:
            project = Path(project).resolve()
            assert project.is_file(), project
            guarded = [p for p in (project, project.parent / 'scene.pkg', project.parent / 'scene.json') if p.is_file()]
            before = {p: hashlib.sha256(p.read_bytes()).digest() for p in guarded}
            integration.command(engine, 'openWallpaper', file=project, playInWindow=name,
                                width=1280, height=720, x=0, y=0, activate=1)
            await asyncio.sleep(1)
            info = await read_cover(source)
            await bridge.publish(source, info, artwork)
            await asyncio.sleep(2.5)
            window = u.FindWindowW(None, name)
            assert window, 'Preview window missing'
            u.SetWindowPos(window, w.HWND(-1), 0, 0, 1280, 760, 0x40)
            await asyncio.sleep(0.1)
            capture = ImageGrab.grab(bbox=(0, 0, 1280, 760))
            folder = DATA / 'verification'
            folder.mkdir(exist_ok=True)
            capture.save(folder / f'{project.parent.name}-universal.png')
            mean = ImageStat.Stat(capture.crop(tuple(map(int, (left, top, right, bottom))))).mean
            assert all(abs(a - b) < 35 for a, b in zip(mean, color)), f'Processed media is not rendered at requested cover region: {mean}'
            integration.command(engine, 'closeWallpaper', location=name)
            bridge.disable()
            assert all(hashlib.sha256(p.read_bytes()).digest() == digest for p, digest in before.items()), 'Wallpaper files changed'
            print(f'PASS: original wallpaper {project.parent.name} renders enhanced media without any file changes', flush=True)
    finally:
        bridge.close()
        if u.FindWindowW(None, name) and integration.engine_running():
            integration.command(engine, 'closeWallpaper', location=name)
        u.ShowWindow(foreground, 3 if was_maximized else 9)


async def run(args):
    manager = await Manager.request_async()
    await check_worker(manager, args.external_helper, args.require_hd)
    await check_wallpapers(manager, args.case)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external-helper', action='store_true')
    parser.add_argument('--require-hd', action='store_true', help='Require verified original artwork from an external helper')
    parser.add_argument('--case', nargs=5, action='append', default=[],
                        metavar=('PROJECT', 'LEFT', 'TOP', 'RIGHT', 'BOTTOM'))
    asyncio.run(run(parser.parse_args()))
