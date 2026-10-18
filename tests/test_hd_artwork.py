import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from wallpaper_cover_sr import backend, covers, netease_artwork as hd


def artwork(color='teal'):
    image = Image.new('RGB', (1200, 1200), '#eaeef6')
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 70, 800, 430), fill=color)
    draw.ellipse((400, 450, 1130, 1160), fill='#b63a28')
    for x in range(100, 900, 120):
        draw.line((x, 250, x + 180, 980), fill='#182030', width=17)
    return image


def png(image):
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


class HDTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.playlist = self.root / 'playingList'
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        patcher = patch.object(hd, 'CACHE', self.cache)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.image = artwork()
        self.info = {'app': 'cloudmusic.exe', 'title': 'Test song', 'artist': 'Artist',
                     'album': '', 'data': png(self.image.resize((135, 135), Image.Resampling.LANCZOS))}
        self.settings = {'prefer_hd': True, 'netease_playlist': str(self.playlist)}
        self.write_tracks()

    def write_tracks(self, artist='Artist', urls=None):
        urls = urls or ['https://p4.music.126.net/cover/123.jpg']
        self.playlist.write_text(json.dumps({'list': [{'track': {
            'id': n + 1, 'name': 'Test song', 'artists': [{'name': artist}],
            'album': {'id': n, 'name': 'Album', 'picUrl': url}}}
            for n, url in enumerate(urls)]}), 'utf-8')

    def test_verified_hd_bypasses_inference_and_reuses_cache_without_network(self):
        with patch.object(hd, 'fetch', return_value=png(self.image)) as fetch, \
             patch.object(backend, 'process', side_effect=AssertionError('HD must not invoke AI')):
            result = covers.process(self.info, self.settings)
        self.assertEqual(result['artwork_source'], 'netease-original')
        self.assertEqual(result['original_size'], [1200, 1200])
        self.assertEqual(result['output'], [1024, 1024])
        self.assertEqual(result['model'], 'none')
        self.assertFalse(result['cache_hit'])
        fetch.assert_called_once()
        with patch.object(hd, 'fetch', side_effect=AssertionError('Cache must avoid network')):
            repeated, reason = hd.resolve(self.info, self.settings)
        self.assertFalse(reason)
        self.assertTrue(repeated['cache_hit'])

    def test_same_title_wrong_artist_is_not_downloaded(self):
        self.write_tracks(artist='Other artist')
        with patch.object(hd, 'fetch') as fetch:
            result, reason = hd.resolve(self.info, self.settings)
        self.assertIsNone(result)
        self.assertTrue(reason)
        fetch.assert_not_called()

    def test_lead_artist_only_smtc_matches_collaboration_with_verified_artwork(self):
        document = json.loads(self.playlist.read_text('utf-8'))
        document['list'][0]['track']['artists'].append({'name': 'Guest vocalist'})
        self.playlist.write_text(json.dumps(document), 'utf-8')
        with patch.object(hd, 'fetch', return_value=png(self.image)):
            result, reason = hd.resolve(self.info, self.settings)
        self.assertFalse(reason)
        self.assertEqual(result['artwork_source'], 'netease-original')

    def test_metadata_match_with_wrong_cover_is_rejected(self):
        wrong = self.image.transpose(Image.Transpose.ROTATE_180)
        with patch.object(hd, 'fetch', return_value=png(wrong)):
            result, reason = hd.resolve(self.info, self.settings)
        self.assertIsNone(result)
        self.assertIn('核对', reason)
        self.assertEqual(list(self.cache.glob('*.png')), [])

    def test_cached_artwork_is_rechecked_against_new_thumbnail(self):
        with patch.object(hd, 'fetch', return_value=png(self.image)):
            self.assertIsNotNone(hd.resolve(self.info, self.settings)[0])
        changed = dict(self.info, data=png(self.image.transpose(Image.Transpose.ROTATE_180)))
        with patch.object(hd, 'fetch', side_effect=AssertionError('Existing cache must be used')):
            result, _ = hd.resolve(changed, self.settings)
        self.assertIsNone(result)

    def test_ambiguous_versions_are_not_published(self):
        self.write_tracks(urls=['https://p3.music.126.net/a/1.jpg', 'https://p4.music.126.net/b/2.jpg'])
        with patch.object(hd, 'fetch', return_value=png(self.image)):
            result, reason = hd.resolve(self.info, self.settings)
        self.assertIsNone(result)
        self.assertIn('多个版本', reason)

    def test_disabled_online_option_never_reads_queue_or_fetches(self):
        baseline = {'file': 'offline.png', 'input': [135, 135], 'output': [540, 540]}
        with patch.object(hd, 'resolve', side_effect=AssertionError('Online path disabled')), \
             patch.object(backend, 'process', return_value=baseline):
            result = covers.process(self.info, {'prefer_hd': False})
        self.assertEqual(result['artwork_source'], 'super-resolution')

    def test_network_failure_falls_back_and_schedules_bounded_retry(self):
        baseline = {'file': 'offline.png', 'input': [135, 135], 'output': [540, 540]}
        with patch.object(hd, 'fetch', side_effect=TimeoutError('offline')), \
             patch.object(backend, 'process', return_value=baseline) as fallback:
            result = covers.process(self.info, self.settings)
        self.assertEqual(result['artwork_source'], 'super-resolution')
        self.assertTrue(result['hd_retry'])
        fallback.assert_called_once()

    def test_cancellation_during_fetch_never_starts_fallback_inference(self):
        with patch.object(hd, 'fetch', side_effect=backend.Cancelled()), \
             patch.object(backend, 'process') as fallback:
            with self.assertRaises(backend.Cancelled):
                covers.process(self.info, self.settings)
        fallback.assert_not_called()

    def test_wrong_album_and_unsupported_playlist_format_fall_back(self):
        with patch.object(hd, 'fetch') as fetch:
            self.assertIsNone(hd.resolve(dict(self.info, album='Other album'), self.settings)[0])
            self.playlist.write_text('[]', 'utf-8')
            self.assertIsNone(hd.resolve(self.info, self.settings)[0])
        fetch.assert_not_called()

    def test_foreign_hosts_credentials_ports_and_redirects_are_rejected(self):
        for url in ['https://example.com/a.jpg', 'https://p3.music.126.net.evil.test/a.jpg',
                    'https://p3.music.126.net:443/a.jpg', 'https://user@p3.music.126.net/a.jpg',
                    'file:///a.jpg']:
            with self.subTest(url=url), self.assertRaises(hd.Unavailable):
                hd.cdn_url(url)
        with self.assertRaises(hd.Unavailable):
            hd.CDNRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com/a.jpg')
        self.assertEqual(hd.cdn_url('http://p3.music.126.net/a.jpg?param=135y135'),
                         'https://p3.music.126.net/a.jpg')

    def test_blank_thumbnail_cannot_verify_identity(self):
        self.assertFalse(hd.same_artwork(Image.new('RGB', (135, 135), 'white'),
                                         Image.new('RGB', (1024, 1024), 'white')))
