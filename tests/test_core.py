import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from wallpaper_cover_sr import backend, integration


class EngineTests(unittest.TestCase):
    def test_command_does_not_launch_an_inactive_engine(self):
        with patch.object(integration, 'engine_running', return_value=False), patch.object(integration.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                integration.command('unused', 'applyProperties', properties={})
            run.assert_not_called()


class BackendTests(unittest.TestCase):
    def image_bytes(self):
        stream = io.BytesIO()
        Image.new('RGB', (8, 8), '#5199c5').save(stream, 'PNG')
        return stream.getvalue()

    def test_cached_four_x_can_supply_other_scales_without_inference(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(backend, 'CACHE', Path(folder)):
            data = self.image_bytes()
            settings = {'model': 'realesrgan-x4plus', 'scale': 4}
            digest = backend.hashlib.sha256(data + b'realesrgan-x4plusofficial-20220424-v1').hexdigest()
            Image.new('RGB', (32, 32), '#5199c5').save(Path(folder) / f'{digest}-x4.png')
            with patch.object(backend.subprocess, 'Popen', side_effect=AssertionError('No inference expected')):
                for scale in (2, 3, 4):
                    result = backend.process(data, dict(settings, scale=scale))
                    self.assertEqual(result['output'], [8 * scale, 8 * scale])

    def test_invalid_multiplier_rejected_before_execution(self):
        with self.assertRaises(ValueError):
            backend.process(self.image_bytes(), {'model': 'realesrgan-x4plus', 'scale': 16})

    def test_cached_result_is_not_published_after_cancellation(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(backend, 'CACHE', Path(folder)):
            stream = io.BytesIO()
            Image.new('RGB', (512, 512)).save(stream, 'PNG')
            with self.assertRaises(backend.Cancelled):
                backend.process(stream.getvalue(), {'model': 'realesrgan-x4plus', 'scale': 4}, lambda: True)


if __name__ == '__main__':
    unittest.main()
