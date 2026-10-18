import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from wallpaper_cover_sr.media_policy import APP_ID, choose_source
from wallpaper_cover_sr.media_bridge import MediaBridge, SystemMediaTransportControlsButton
from wallpaper_cover_sr import worker


class SelectionTests(unittest.TestCase):
    def test_never_selects_its_own_published_artwork(self):
        self.assertIsNone(choose_source([{'id': APP_ID, 'playing': True}], APP_ID))

    def test_preserves_real_source_when_proxy_is_current(self):
        sources = [{'id': APP_ID, 'playing': True}, {'id': 'cloudmusic.exe', 'playing': True}]
        self.assertEqual(choose_source(sources, APP_ID, 'cloudmusic.exe'), 'cloudmusic.exe')

    def test_new_external_player_can_take_over(self):
        sources = [{'id': 'cloudmusic.exe', 'playing': True}, {'id': 'Spotify.exe', 'playing': True}]
        self.assertEqual(choose_source(sources, 'Spotify.exe', 'cloudmusic.exe'), 'Spotify.exe')

    def test_does_not_keep_paused_player_over_new_playing_source(self):
        sources = [{'id': 'cloudmusic.exe', 'playing': False}, {'id': 'chrome.exe', 'playing': True}]
        self.assertEqual(choose_source(sources, APP_ID, 'cloudmusic.exe'), 'chrome.exe')

    def test_explicit_preference_waits_instead_of_using_another_player(self):
        self.assertIsNone(choose_source([{'id': 'chrome.exe', 'playing': True}], preferred_id='cloudmusic.exe'))

    def test_closed_sources_are_ignored(self):
        self.assertIsNone(choose_source([{'id': 'cloudmusic.exe', 'closed': True}], 'cloudmusic.exe'))


class BridgeButtonTests(unittest.IsolatedAsyncioTestCase):
    async def test_pause_button_reaches_original_player_asynchronously(self):
        paused = asyncio.Event()
        class Source:
            async def try_pause_async(self):
                paused.set()
                return True
        bridge = MediaBridge.__new__(MediaBridge)
        bridge.loop = asyncio.get_running_loop()
        bridge.closed = False
        bridge.source = Source()
        bridge._button(None, SimpleNamespace(button=SystemMediaTransportControlsButton.PAUSE))
        await asyncio.wait_for(paused.wait(), 1)


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_universal_worker_needs_no_wallpaper_path_and_closes_proxy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / 'enhanced.png'
            image.write_bytes(b'processed image')
            settings = SimpleNamespace(get=lambda: {'enabled': True, 'scale': 4,
                'model': 'realesrgan-x4plus', 'cache_mb': 128, 'source_app': ''})
            source = SimpleNamespace(source_app_user_model_id='cloudmusic.exe',
                get_playback_info=lambda: SimpleNamespace(playback_status=worker.PlaybackStatus.PLAYING),
                add_media_properties_changed=lambda callback: 1,
                add_playback_info_changed=lambda callback: 2,
                remove_media_properties_changed=lambda token: None,
                remove_playback_info_changed=lambda token: None)
            manager = SimpleNamespace(get_sessions=lambda: [source], get_current_session=lambda: source,
                add_sessions_changed=lambda callback: 1, add_current_session_changed=lambda callback: 2,
                remove_sessions_changed=lambda token: None, remove_current_session_changed=lambda token: None)
            class Manager:
                @staticmethod
                async def request_async(): return manager
            info = {'title': 'Test song', 'artist': 'Test artist', 'hash': 'cover hash', 'data': b'original'}
            async def cover(session): return dict(info)
            result = {'file': str(image), 'input': [135, 135], 'output': [540, 540],
                      'cache_hit': False, 'seconds': 0.01, 'model': 'realesrgan-x4plus'}
            service = worker.Worker(settings)
            class Bridge:
                instance = None
                def __init__(self, loop):
                    self.enabled = False; self.closed = False; self.published = None
                    Bridge.instance = self
                def disable(self): self.enabled = False
                async def publish(self, original, metadata, data):
                    self.published = (original, metadata, data)
                    self.enabled = True
                    service.stop()
                def sync(self, original, reclaim=False): pass
                def close(self): self.closed = True
            with patch.object(worker, 'DATA', root), patch.object(worker, 'Manager', Manager), \
                 patch.object(worker, 'MediaBridge', Bridge), patch.object(worker, 'read_cover', cover), \
                 patch.object(worker.integration, 'engine_running', return_value=True), \
                 patch.object(worker.integration, 'selected', side_effect=AssertionError('Must not inspect wallpapers')), \
                 patch.object(worker.backend, 'process', return_value=result), patch.object(worker.backend, 'trim_cache'):
                await asyncio.wait_for(service.run(), 2)
            self.assertEqual(Bridge.instance.published[2], b'processed image')
            self.assertIs(Bridge.instance.published[0], source)
            self.assertTrue(Bridge.instance.closed)

    async def test_stale_processed_cover_is_not_published_after_song_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); image = root / 'cover.png'; image.write_bytes(b'processed')
            settings = SimpleNamespace(get=lambda: {'enabled': True, 'scale': 4,
                'model': 'realesrgan-x4plus', 'cache_mb': 128, 'source_app': ''})
            source = SimpleNamespace(source_app_user_model_id='cloudmusic.exe',
                get_playback_info=lambda: SimpleNamespace(playback_status=worker.PlaybackStatus.PLAYING),
                add_media_properties_changed=lambda callback: 1, add_playback_info_changed=lambda callback: 2,
                remove_media_properties_changed=lambda token: None, remove_playback_info_changed=lambda token: None)
            manager = SimpleNamespace(get_sessions=lambda: [source], get_current_session=lambda: source,
                add_sessions_changed=lambda callback: 1, add_current_session_changed=lambda callback: 2,
                remove_sessions_changed=lambda token: None, remove_current_session_changed=lambda token: None)
            class Manager:
                @staticmethod
                async def request_async(): return manager
            service = worker.Worker(settings)
            reads = 0
            async def cover(session):
                nonlocal reads
                reads += 1
                if reads > 1: service.stop()
                return {'title': 'new' if reads > 1 else 'old', 'artist': 'artist',
                        'hash': 'new' if reads > 1 else 'old', 'data': b'original'}
            class Bridge:
                enabled = False
                def __init__(self, loop): pass
                def disable(self): pass
                async def publish(self, *args): self.fail('Stale artwork must never be published')
                def close(self): pass
            async def must_not_publish(*args):
                raise AssertionError('Stale artwork was published')
            Bridge.publish = must_not_publish
            result = {'file': str(image), 'input': [135, 135], 'output': [540, 540],
                      'cache_hit': False, 'seconds': 0.01, 'model': 'realesrgan-x4plus'}
            with patch.object(worker, 'DATA', root), patch.object(worker, 'Manager', Manager), \
                 patch.object(worker, 'MediaBridge', Bridge), patch.object(worker, 'read_cover', cover), \
                 patch.object(worker.integration, 'engine_running', return_value=True), \
                 patch.object(worker.backend, 'process', return_value=result):
                await asyncio.wait_for(service.run(), 2)
