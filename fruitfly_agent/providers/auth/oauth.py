"""Bounded loopback authorization attempts; no terminal input ownership."""
from __future__ import annotations
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

class OAuthAttempt:
    def __init__(self, *, client_id: str = '', port: int = 0):
        self.state, self.nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.verifier = secrets.token_urlsafe(48)
        self.challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).decode().rstrip('=')
        self.client_id = client_id
        self.result: dict[str, str] | None = None
        self.error = ''
        self.finished = threading.Event()
        self.started = time.monotonic()
        self.closed = False
        attempt = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                try:
                    attempt.accept(f'http://127.0.0.1:{attempt.server.server_port}' + self.path)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'Authorization received. Return to FruitFlyAgent.')
                except ValueError:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'Invalid authorization callback.')
            def log_message(self, format: str, *args: Any) -> None:
                pass
        class CallbackServer(HTTPServer):
            def get_request(self) -> tuple[Any, Any]:
                connection, address = super().get_request()
                connection.settimeout(2)
                return connection, address
        self.server = CallbackServer(('127.0.0.1', port), Handler)
        self.redirect_uri = f'http://127.0.0.1:{self.server.server_port}/auth/callback'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def accept(self, url: str) -> None:
        parsed, expected = urlsplit(url), urlsplit(self.redirect_uri)
        if parsed.scheme != expected.scheme or parsed.netloc != expected.netloc or parsed.path != expected.path or parsed.fragment:
            raise ValueError('Callback must match the pending local authorization URL')
        query = parse_qs(parsed.query, keep_blank_values=True)
        if any(len(v) != 1 for v in query.values()) or query.get('state', [''])[0] != self.state:
            raise ValueError('Authorization state mismatch')
        if self.finished.is_set() or time.monotonic() - self.started > 300:
            raise ValueError('Authorization attempt has expired')
        if 'error' in query:
            self.error = 'Authorization declined; no model changes applied'
            self.finished.set()
            return
        issued = query.get('client_id', [self.client_id])[0]
        if not issued or issued == 'dynamic_agent_client' or (self.client_id and issued != self.client_id):
            raise ValueError('Authorization client registration mismatch')
        code = query.get('code', [''])[0]
        if not code:
            raise ValueError('Authorization code is missing')
        self.result = {'code': code, 'client_id': issued}
        self.finished.set()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
