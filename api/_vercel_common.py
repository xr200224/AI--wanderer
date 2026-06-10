import json
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler

import rapidapi_proxy as proxy


class JsonHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def query_params(self) -> dict[str, list[str]]:
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

    def send_exception(self, exc: Exception):
        self.send_json(502, {
            "ok": False,
            "error": str(exc),
            "trace": traceback.format_exc(limit=3),
        })


def first_param(params: dict[str, list[str]], *names: str, default: str = "") -> str:
    for name in names:
        values = params.get(name)
        if values:
            return values[0].strip()
    return default


def int_param(params: dict[str, list[str]], name: str, default: int, min_value: int, max_value: int) -> int:
    try:
        raw = first_param(params, name, default=str(default))
        value = int(raw or default)
    except ValueError:
        value = default
    return max(min_value, min(value, max_value))
