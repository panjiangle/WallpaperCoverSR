"""Publish enhanced artwork through the public Windows SMTC interface.

There is no wallpaper adapter: original scene and web wallpapers consume the
same OS media events they already use. No audio source or silent playback is
created. Play/pause/seek requests are forwarded to the real player.
"""
import asyncio
from collections import deque
import ctypes
import logging

from winrt.windows.media import (
    MediaPlaybackStatus, MediaPlaybackType, SystemMediaTransportControlsButton,
    SystemMediaTransportControlsTimelineProperties,
)
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as SourceStatus
from winrt.windows.media.playback import MediaPlayer
from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream, RandomAccessStreamReference

from .media_policy import APP_ID

LOG = logging.getLogger(__name__)
STATUS = {SourceStatus.PLAYING: MediaPlaybackStatus.PLAYING,
          SourceStatus.PAUSED: MediaPlaybackStatus.PAUSED,
          SourceStatus.CHANGING: MediaPlaybackStatus.CHANGING,
          SourceStatus.STOPPED: MediaPlaybackStatus.STOPPED,
          SourceStatus.CLOSED: MediaPlaybackStatus.CLOSED,
          SourceStatus.OPENED: MediaPlaybackStatus.PAUSED}
BUTTONS = {
    SystemMediaTransportControlsButton.PLAY: 'try_play_async',
    SystemMediaTransportControlsButton.PAUSE: 'try_pause_async',
    SystemMediaTransportControlsButton.STOP: 'try_stop_async',
    SystemMediaTransportControlsButton.NEXT: 'try_skip_next_async',
    SystemMediaTransportControlsButton.PREVIOUS: 'try_skip_previous_async',
}


class MediaBridge:
    def __init__(self, loop):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        self.loop = loop
        self.source = None
        self.player = MediaPlayer()
        self.player.command_manager.is_enabled = False
        self.player.is_muted = True
        self.controls = self.player.system_media_transport_controls
        self.controls.is_enabled = False
        self.updater = self.controls.display_updater
        self.updater.type = MediaPlaybackType.MUSIC
        self.streams = deque()
        self.enabled = False
        self.closed = False
        self.button_token = self.controls.add_button_pressed(self._button)
        self.seek_token = self.controls.add_playback_position_change_requested(self._seek)

    def _schedule(self, operation):
        if self.closed or self.loop.is_closed():
            return
        async def forward():
            return await asyncio.wait_for(operation, 5)
        future = asyncio.run_coroutine_threadsafe(forward(), self.loop)
        def done(result):
            try:
                result.result()
            except Exception:
                LOG.exception('Player control forwarding failed')
        future.add_done_callback(done)

    def _button(self, sender, args):
        method = BUTTONS.get(args.button)
        if method and self.source:
            self._schedule(getattr(self.source, method)())

    def _seek(self, sender, args):
        if self.source:
            position = int(args.requested_playback_position.total_seconds() * 10_000_000)
            self._schedule(self.source.try_change_playback_position_async(position))

    async def publish(self, source, info, image_bytes):
        self.source = source
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        try:
            writer.write_bytes(image_bytes)
            await asyncio.wait_for(writer.store_async(), 5)
            writer.detach_stream()
        finally:
            writer.close()
        stream.seek(0)
        self.updater.thumbnail = RandomAccessStreamReference.create_from_stream(stream)
        music = self.updater.music_properties
        music.title = info['title']
        music.artist = info['artist']
        music.album_title = info.get('album', '')
        music.album_artist = info.get('album_artist', '')
        music.track_number = info.get('track_number', 0)
        # A fresh manual session must first become active; no audio is played.
        # Apply the source's real state immediately after publishing metadata.
        self.controls.playback_status = MediaPlaybackStatus.PLAYING
        self.controls.is_enabled = True
        self.enabled = True
        self.updater.update()
        self.streams.append(stream)
        while len(self.streams) > 2:
            self.streams.popleft().close()
        self.sync(source)

    def sync(self, source):
        if not self.enabled:
            return
        self.source = source
        info = source.get_playback_info()
        controls = info.controls
        for name in ('is_play_enabled', 'is_pause_enabled', 'is_stop_enabled',
                     'is_next_enabled', 'is_previous_enabled'):
            setattr(self.controls, name, getattr(controls, name))
        desired = STATUS.get(info.playback_status, MediaPlaybackStatus.PAUSED)
        if self.controls.playback_status != desired:
            self.controls.playback_status = desired
        timeline = source.get_timeline_properties()
        if timeline.end_time >= timeline.start_time:
            update = SystemMediaTransportControlsTimelineProperties()
            update.start_time = timeline.start_time
            update.end_time = timeline.end_time
            update.position = min(max(timeline.position, timeline.start_time), timeline.end_time)
            update.min_seek_time = max(timeline.start_time, timeline.min_seek_time)
            update.max_seek_time = min(timeline.end_time, max(update.min_seek_time, timeline.max_seek_time))
            self.controls.update_timeline_properties(update)

    def disable(self):
        if self.enabled:
            self.controls.is_enabled = False
            self.enabled = False
        self.source = None

    def close(self):
        if self.closed:
            return
        self.disable()
        self.closed = True
        self.controls.remove_button_pressed(self.button_token)
        self.controls.remove_playback_position_change_requested(self.seek_token)
        self.player.close()
        while self.streams:
            self.streams.popleft().close()
