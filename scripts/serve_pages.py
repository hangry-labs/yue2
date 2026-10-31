"""Serve the generated website under the real /yue2 project prefix."""
import argparse
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PREFIX = '/yue2'


def handler(root):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def end_headers(self):
            self.send_header('Accept-Ranges', 'bytes')
            super().end_headers()

        def send_head(self):
            self.byte_range = None
            path = Path(self.translate_path(self.path))
            requested = self.headers.get('Range')
            if not requested or not path.is_file():
                return super().send_head()
            size = path.stat().st_size
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            if not match or not any(match.groups()):
                start, end = size, 0
            elif not match[1]:
                start, end = max(0, size - int(match[2])), size - 1
            else:
                start = int(match[1])
                end = min(int(match[2]), size - 1) if match[2] else size - 1
            if start >= size or end < start:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return None
            stream = path.open('rb')
            stream.seek(start)
            self.byte_range = end - start + 1
            self.send_response(206)
            self.send_header('Content-Type', self.guess_type(str(path)))
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.send_header('Content-Length', str(self.byte_range))
            self.send_header('Last-Modified', self.date_time_string(path.stat().st_mtime))
            self.end_headers()
            return stream

        def copyfile(self, source, output):
            if self.byte_range is None:
                return super().copyfile(source, output)
            remaining = self.byte_range
            while remaining:
                chunk = source.read(min(65536, remaining))
                if not chunk:
                    break
                output.write(chunk)
                remaining -= len(chunk)

        def do_GET(self):
            if self.path in ('/', PREFIX):
                self.send_response(302)
                self.send_header('Location', PREFIX + '/')
                self.end_headers()
                return
            if not urlsplit(self.path).path.startswith(PREFIX + '/'):
                self.send_error(404)
                return
            self.path = self.path[len(PREFIX):]
            super().do_GET()

        def do_HEAD(self):
            if not urlsplit(self.path).path.startswith(PREFIX + '/'):
                self.send_error(404)
                return
            self.path = self.path[len(PREFIX):]
            super().do_HEAD()
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent / 'build/pages/output')
    parser.add_argument('--port', type=int, default=9005)
    parser.add_argument('--bind', default='127.0.0.1')
    args = parser.parse_args()
    print(f'Serving http://{args.bind}:{args.port}{PREFIX}/', flush=True)
    ThreadingHTTPServer((args.bind, args.port), handler(args.root)).serve_forever()
