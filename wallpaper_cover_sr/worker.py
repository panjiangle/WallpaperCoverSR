"""Event-driven real-player -> super-resolution -> Windows media bridge."""
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import threading
import time

from winrt.runtime import ApartmentType, init_apartment, uninit_apartment
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as Manager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winrt.windows.storage.streams import DataReader

from . import backend, covers, integration
from .config import DATA
from .media_bridge import MediaBridge
from .media_policy import choose_source, is_own_session

LOG = logging.getLogger(__name__)


async def read_cover(session):
    props = await asyncio.wait_for(session.try_get_media_properties_async(), 5)
    if not props.title or not props.thumbnail:
        return None
    stream = await asyncio.wait_for(props.thumbnail.open_read_async(), 5)
    try:
        if not 0 < stream.size <= 16 * 1024 * 1024:
            raise ValueError('封面文件大小异常')
        reader = DataReader(stream)
        try:
            n = await asyncio.wait_for(reader.load_async(stream.size), 5)
            if n != stream.size:
                raise ValueError('封面未读取完整')
            data = bytearray(n)
            reader.read_bytes(data)
        finally:
            reader.detach_stream()
            reader.close()
    finally:
        stream.close()
    return {'title': props.title, 'artist': props.artist,
            'album': props.album_title, 'album_artist': props.album_artist,
            'track_number': props.track_number, 'app': session.source_app_user_model_id,
            'data': bytes(data), 'hash': hashlib.sha256(data).hexdigest()}


def source_snapshot(manager):
    sessions, descriptors = {}, []
    for session in manager.get_sessions():
        app_id = session.source_app_user_model_id
        if is_own_session(app_id):
            continue
        try:
            status = session.get_playback_info().playback_status
        except Exception:
            continue
        sessions[app_id] = session
        descriptors.append({'id': app_id, 'playing': status == PlaybackStatus.PLAYING,
                            'closed': status == PlaybackStatus.CLOSED})
    current = manager.get_current_session()
    current_id = current.source_app_user_model_id if current else ''
    if current and current_id in sessions:
        sessions[current_id] = current
    return sessions, descriptors, current_id


class Worker:
    def __init__(self, settings):
        self.settings = settings
        self.quit = threading.Event()
        self.loop = None
        self.dirty = None
        self.revision = 0
        self.lock = threading.Lock()
        self.info = {'message': '正在启动通用模式…', 'state': 'starting'}
        self.thread = threading.Thread(target=self._thread, name='CoverSR', daemon=True)

    def update(self, message, **details):
        info = dict(message=message, **details)
        with self.lock:
            if self.info == info:
                return
            self.info = info
        (DATA / 'status.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), 'utf-8')

    def get_info(self):
        with self.lock:
            return dict(self.info)

    def wake(self, *args):
        if self.loop and not self.loop.is_closed() and self.dirty is not None:
            self.loop.call_soon_threadsafe(self.dirty.set)

    def poke(self, *args):
        # Only a real cover/settings change invalidates inference. Events caused
        # by publishing our own session wake the loop without cancelling work.
        self.revision += 1
        self.wake()

    def stop(self):
        self.quit.set()
        self.poke()

    def _thread(self):
        init_apartment(ApartmentType.MULTI_THREADED)
        try:
            asyncio.run(self.run())
        except Exception:
            LOG.exception('Worker stopped unexpectedly')
            self.update('后台服务异常，请查看日志后重新启动', state='error')
        finally:
            uninit_apartment()

    @staticmethod
    def unsubscribe(session, tokens):
        if session and tokens:
            for method, token in zip(('remove_media_properties_changed', 'remove_playback_info_changed'), tokens):
                try:
                    getattr(session, method)(token)
                except Exception:
                    pass

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.dirty = asyncio.Event()
        manager = None
        manager_tokens = []
        session = None
        session_id = ''
        source_tokens = []
        bridge = None
        last_key = None
        last_file = ''
        published_info = None
        next_reclaim = 0
        next_poll = 0
        next_hd_retry = float('inf')
        try:
            while not self.quit.is_set():
                try:
                    settings = self.settings.get()
                    if not settings['enabled']:
                        if bridge:
                            bridge.disable()
                        last_key = None
                        self.update('已关闭：由播放器提供原始封面', state='disabled')
                        await self.wait(5)
                        continue
                    if not integration.engine_running():
                        if bridge:
                            bridge.disable()
                        last_key = None
                        self.update('等待 Wallpaper Engine 启动…', state='waiting')
                        await self.wait(5)
                        continue
                    if manager is None:
                        manager = await asyncio.wait_for(Manager.request_async(), 10)
                        manager_tokens = [manager.add_sessions_changed(self.wake),
                                          manager.add_current_session_changed(self.wake)]
                    if bridge is None:
                        bridge = MediaBridge(self.loop)
                    sessions, sources, current_id = source_snapshot(manager)
                    chosen = choose_source(sources, current_id, session_id, settings.get('source_app', ''))
                    if chosen is None:
                        bridge.disable()
                        self.unsubscribe(session, source_tokens)
                        session = None
                        session_id = ''
                        source_tokens = []
                        last_key = None
                        self.update('等待播放器提供歌曲和封面…', state='waiting')
                        await self.wait(5)
                        continue
                    if chosen != session_id or session is None:
                        bridge.disable()
                        self.unsubscribe(session, source_tokens)
                        session = sessions[chosen]
                        session_id = chosen
                        source_tokens = [session.add_media_properties_changed(self.poke),
                                         session.add_playback_info_changed(self.wake)]
                        self.revision += 1
                        last_key = None
                        next_poll = 0
                    dirty = self.dirty.is_set()
                    self.dirty.clear()
                    revision = self.revision
                    if dirty or last_key is None or time.monotonic() >= next_poll:
                        current = await read_cover(session)
                        next_poll = time.monotonic() + 30
                        if current is None:
                            bridge.disable()
                            last_key = None
                            self.update('播放器暂未提供封面', state='waiting', source_app=session_id)
                        else:
                            key = (session_id, current['title'], current['artist'], current['hash'],
                                   settings['scale'], settings['model'], settings.get('prefer_hd', False),
                                   settings.get('netease_playlist', ''))
                            if key != last_key or time.monotonic() >= next_hd_retry:
                                if key != last_key:
                                    bridge.disable()
                                self.update('正在获取高清原封面…' if settings.get('prefer_hd') else '正在处理封面…', state='processing',
                                            title=current['title'], source_app=session_id)
                                result = await asyncio.to_thread(covers.process, current, settings,
                                    lambda: self.quit.is_set() or self.revision != revision or not self.settings.get()['enabled'])
                                latest = await read_cover(session)
                                if latest is None or any(latest[k] != current[k] for k in ('title', 'artist', 'hash')):
                                    continue
                                if self.revision != revision or not self.settings.get()['enabled'] or self.quit.is_set():
                                    continue
                                _, newest_sources, newest_current = source_snapshot(manager)
                                if choose_source(newest_sources, newest_current, session_id, settings.get('source_app', '')) != session_id:
                                    continue
                                if not bridge.enabled or key != last_key or result['file'] != last_file:
                                    await bridge.publish(session, latest, Path(result['file']).read_bytes())
                                    published_info = latest
                                last_file = result['file']
                                last_key = key
                                next_hd_retry = time.monotonic() + 60 if result.get('hd_retry') else float('inf')
                                if result.get('artwork_source') == 'netease-original':
                                    size = result['original_size']
                                    message = f'高清原封面 {size[0]}×{size[1]} · 直接显示，未超分'
                                else:
                                    message = f'{result["input"][0]}×{result["input"][1]} → {result["output"][0]}×{result["output"][1]}'
                                    if result.get('hd_note'):
                                        message += ' · 高清原图暂不可用，已回退'
                                self.update(message,
                                    state='ready', title=latest['title'], artist=latest['artist'],
                                    source_app=session_id, mode='windows-media-bridge', **result)
                                LOG.info('Universal cover ready: %sx%s -> %sx%s, cache=%s',
                                         *result['input'], *result['output'], result['cache_hit'])
                                backend.trim_cache(settings['cache_mb'], {result['file']})
                    if bridge.enabled and session:
                        actual = manager.get_current_session()
                        actual_id = actual.source_app_user_model_id if actual else ''
                        if actual_id == session_id and time.monotonic() >= next_reclaim:
                            newest = await read_cover(session)
                            if newest is None or any(newest[k] != published_info[k]
                                                     for k in ('title', 'artist', 'hash')):
                                self.poke()
                                continue
                            if (self.quit.is_set() or self.revision != revision
                                    or not self.settings.get()['enabled']):
                                continue
                            _, recovery_sources, recovery_current = source_snapshot(manager)
                            if choose_source(recovery_sources, recovery_current, session_id,
                                             self.settings.get().get('source_app', '')) != session_id:
                                self.wake()
                                continue
                            # Updating metadata on an existing SMTC session does not
                            # restore Windows' current-session selection. Recreate
                            # only after our real source takes over; reuse its PNG.
                            bridge.close()
                            bridge = MediaBridge(self.loop)
                            await bridge.publish(session, newest, Path(last_file).read_bytes())
                            next_reclaim = time.monotonic() + 2
                            LOG.info('Restored enhanced media session after source takeover')
                        else:
                            bridge.sync(session)
                        if actual_id == session_id:
                            await self.wait(min(8, max(0.1, next_reclaim - time.monotonic())))
                            continue
                    await self.wait(8)
                except backend.Cancelled:
                    last_key = None
                except Exception as exc:
                    LOG.exception('Universal cover update failed')
                    if bridge:
                        bridge.disable()
                    self.update(str(exc), state='error')
                    self.unsubscribe(session, source_tokens)
                    session = None
                    session_id = ''
                    source_tokens = []
                    last_key = None
                    await self.wait(5)
        finally:
            self.unsubscribe(session, source_tokens)
            if manager and manager_tokens:
                manager.remove_sessions_changed(manager_tokens[0])
                manager.remove_current_session_changed(manager_tokens[1])
            if bridge:
                bridge.close()

    async def wait(self, seconds):
        try:
            await asyncio.wait_for(self.dirty.wait(), seconds)
        except asyncio.TimeoutError:
            pass
        if self.get_info().get('state') in ('disabled', 'waiting', 'error'):
            self.dirty.clear()
