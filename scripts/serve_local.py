"""Serve the brainstorm HTTP API on localhost, so the frontend can run without AWS.

Usage: python scripts/serve_local.py [--endpoint-url URL] [--table NAME] [--port N]

Each request is turned into the same API Gateway (HTTP API, payload 2.0) event that Lambda would
get and passed to ``brainstorm.api.handle``, so local runs and AWS share one code path.
"""

import argparse
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from brainstorm import api, db  # noqa: E402 - needs the sys.path entry above


def to_event(method: str, target: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    """Build an API Gateway payload 2.0 event from a raw HTTP request line, headers and body."""
    url = urlsplit(target)
    # API Gateway joins repeated query parameters with commas; do the same.
    query: dict[str, str] = {}
    for name, value in parse_qsl(url.query, keep_blank_values=True):
        query[name] = f"{query[name]},{value}" if name in query else value
    return {
        "version": "2.0",
        "rawPath": url.path,
        "rawQueryString": url.query,
        "headers": {k.lower(): v for k, v in headers.items()},
        "queryStringParameters": query or None,
        "requestContext": {"http": {"method": method, "path": url.path}},
        "body": body.decode() if body else None,
        "isBase64Encoded": False,
    }


def make_handler(table) -> type[BaseHTTPRequestHandler]:
    """Return a request handler class that sends every request to the API using ``table``."""

    class Handler(BaseHTTPRequestHandler):
        def _dispatch(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            event = to_event(self.command, self.path, dict(self.headers.items()), body)
            try:
                resp = api.handle(table, event)
            except Exception:
                api.logger.exception("unhandled error")
                resp = api.error(500, "internal_error", "something went wrong")
            payload = resp["body"].encode()
            self.send_response(resp["statusCode"])
            for name, value in resp["headers"].items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        # http.server looks up handlers by these exact names.
        do_GET = do_POST = do_PUT = do_DELETE = do_OPTIONS = do_PATCH = _dispatch  # noqa: N815

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint-url", default=db.endpoint_url(), help="e.g. localhost:8000")
    parser.add_argument("--table", default=db.table_name(), help="table name")
    parser.add_argument("--port", type=int, default=3000, help="port to listen on")
    args = parser.parse_args()

    # One request at a time, like a Lambda container; boto3 resources aren't thread-safe.
    server = HTTPServer(
        ("127.0.0.1", args.port), make_handler(db.table(args.table, args.endpoint_url))
    )
    print(f"Serving the brainstorm API on http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
