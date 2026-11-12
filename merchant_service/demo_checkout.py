"""Local-only payment UI demo. Never redirects to a bank or accepts money/items.

Run: py -3.11 demo_checkout.py. Opens http://127.0.0.1:8797 in a browser.
"""
from __future__ import annotations

import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from external_orders import DemoOrderLedger

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / 'demo_checkout.html'


def main():
    ledger = DemoOrderLedger(ROOT / 'private' / 'external_demo.sqlite3')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, body: bytes, status: int = 200, kind: str = 'application/json; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'")
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/', '/index.html'):
                return self.reply(PAGE.read_bytes(), kind='text/html; charset=utf-8')
            if path == '/api/recent':
                return self.reply(json.dumps({'orders': ledger.recent(10), 'demo': True}, ensure_ascii=False).encode())
            return self.reply(b'{"error":"not_found"}', 404)

        def do_POST(self):
            if self.path != '/api/demo-order':
                return self.reply(b'{"error":"not_found"}', 404)
            origin = self.headers.get('Origin', '')
            if origin and origin != 'http://127.0.0.1:8797':
                return self.reply(b'{"error":"foreign_origin"}', 403)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(b'{"error":"json_required"}', 415)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 1 <= size <= 8192:
                    raise ValueError('size')
                obj = json.loads(self.rfile.read(size).decode('utf-8'))
                if not isinstance(obj, dict):
                    raise ValueError('object required')
                result = ledger.create(plan=obj.get('plan'), method=obj.get('method'),
                                       game=obj.get('game', ''), basket=obj.get('basket', []))
                return self.reply(json.dumps(result, ensure_ascii=False).encode(), 201)
            except (ValueError, TypeError, UnicodeError) as exc:
                return self.reply(json.dumps({'error': str(exc)[:90]}).encode(), 400)

    server = ThreadingHTTPServer(('127.0.0.1', 8797), Handler)
    url = 'http://127.0.0.1:8797/'
    print('DEMO ONLY. No money, no Steam trades, no licence activation.')
    print('Open', url)
    try:
        webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()