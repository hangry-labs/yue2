"""The preview must serve seekable audio under the production project prefix."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.serve_pages import handler


class PagesServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / 'clip.mp3').write_bytes(b'0123456789')
        cls = handler(root)
        cls.log_message = lambda *args: None
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), cls)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/yue2/clip.mp3'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_normal_file_and_audio_byte_ranges(self):
        for value, expected, status in [(None, b'0123456789', 200),
                                        ('bytes=3-6', b'3456', 206),
                                        ('bytes=7-', b'789', 206),
                                        ('bytes=-2', b'89', 206)]:
            request = Request(self.url, headers={'Range': value} if value else {})
            with urlopen(request) as response:
                self.assertEqual(response.status, status)
                self.assertEqual(response.headers['Accept-Ranges'], 'bytes')
                self.assertEqual(response.read(), expected)

    def test_invalid_range_is_explicit(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url, headers={'Range': 'bytes=100-200'}))
        self.assertEqual(error.exception.code, 416)
        self.assertEqual(error.exception.headers['Content-Range'], 'bytes */10')

    def test_file_is_not_exposed_without_project_prefix(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url.replace('/yue2/', '/'))
        self.assertEqual(error.exception.code, 404)
