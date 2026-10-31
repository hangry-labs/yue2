"""Exercise real FFmpeg encoders and protect original recordings."""
from array import array
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

from scripts.audio_formats import PROFILES, convert, probe


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/FFprobe are required')
class AudioFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.wav'
        pcm = array('h')
        for i in range(24000):
            pcm.extend([int(12000 * math.sin(2 * math.pi * 440 * i / 48000)),
                        int(10000 * math.sin(2 * math.pi * 660 * i / 48000))])
        with wave.open(str(self.source), 'wb') as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(48000)
            output.writeframes(pcm.tobytes())

    def test_all_profiles_encode_real_stereo_audio(self):
        original = self.source.read_bytes()
        for name, settings in PROFILES.items():
            with self.subTest(format=name):
                target = self.root / (name + settings['extension'])
                value = convert(self.source, target, name)
                self.assertEqual(value['codec'], settings['codec'])
                self.assertEqual(value['sample_rate'], 48000)
                self.assertEqual(value['channels'], 2)
                self.assertLess(abs(value['seconds'] - 0.5), 0.15)
                self.assertFalse(value['source']['lossy'])
        self.assertEqual(self.source.read_bytes(), original)

    def test_lossless_flac_preserves_pcm_samples(self):
        source = self.root / 'master24.wav'
        convert(self.source, source, 'wav24')
        target = self.root / 'master.flac'
        convert(source, target, 'flac')
        def decode(path):
            return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 's24le', '-'])
        self.assertEqual(decode(source), decode(target))
        self.assertEqual(probe(target)['bits'], 24)

    def test_existing_output_and_input_are_protected(self):
        target = self.root / 'keep.opus'
        target.write_bytes(b'keep this file')
        with self.assertRaises(FileExistsError):
            convert(self.source, target, 'opus')
        self.assertEqual(target.read_bytes(), b'keep this file')
        with self.assertRaises(ValueError):
            convert(self.source, self.source, 'wav16')

    def test_lossy_input_is_recorded_as_lossy_even_for_flac(self):
        compressed = self.root / 'source.mp3'
        convert(self.source, compressed, 'mp3')
        value = convert(compressed, self.root / 'decoded.flac', 'flac')
        self.assertTrue(value['source']['lossy'])
        self.assertFalse(value['encoding']['lossy'])
