"""Run an opt-in Docker check for the Caddy -> nginx proxy trust boundary.

Usage: python -m scripts.verify_proxy_boundary
Uses devicepilot-frontend:${APP_VERSION}; APP_VERSION defaults to phase9-test locally.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = ROOT / "deploy" / "Caddyfile"
NGINX = ROOT / "frontend" / "nginx.conf"
HASH = "$2a$14$TLALtLC3Ieh7Ym95.PZRe.jFsl2KJy3kf2mpgl9rnveKtSoTbpreq"


def frontend_image() -> str:
    """Return the same immutable frontend tag production Compose builds."""
    version = os.getenv("APP_VERSION", "phase9-test").strip()
    if not version:
        raise RuntimeError("APP_VERSION must not be blank")
    return f"devicepilot-frontend:{version}"


def free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def request(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=3) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main() -> int:
    if shutil.which("docker") is None:
        raise SystemExit("Docker is required")
    port = free_port()
    frontend_port = free_port()
    echo = (
        "import json; from http.server import BaseHTTPRequestHandler,HTTPServer; "
        "H=type('H',(BaseHTTPRequestHandler,),{'do_GET':lambda s:(s.send_response(200),s.send_header('Content-Type','application/json'),s.end_headers(),s.wfile.write(json.dumps(dict(s.headers)).encode())), 'log_message':lambda *_:None}); "
        "HTTPServer(('0.0.0.0',8000),H).serve_forever()"
    )
    with tempfile.TemporaryDirectory(prefix="devicepilot-proxy-") as temporary:
        workspace = Path(temporary)
        compose = {
            "services": {
                "caddy": {"image": "caddy:2.11.4-alpine", "environment": {"DEVICEPILOT_DOMAIN": ":80", "ACME_EMAIL": "ops@example.test", "BASIC_AUTH_USERNAME": "operator", "BASIC_AUTH_PASSWORD_HASH": HASH.replace("$", "$$")}, "ports": [f"127.0.0.1:{port}:80"], "volumes": [f"{CADDYFILE.as_posix()}:/etc/caddy/Caddyfile:ro"], "networks": ["edge"]},
                "frontend": {"image": frontend_image(), "ports": [f"127.0.0.1:{frontend_port}:80"], "volumes": [f"{NGINX.as_posix()}:/etc/nginx/conf.d/default.conf:ro"], "networks": ["edge", "app"]},
                "backend": {"image": "python:3.12-alpine", "command": ["python", "-c", echo], "networks": ["app"]},
            },
            "networks": {"edge": {}, "app": {"internal": True}},
        }
        compose_path = workspace / "compose.yml"
        compose_path.write_text(json.dumps(compose), encoding="utf-8")
        command = ["docker", "compose", "-p", f"devicepilot-proxy-{port}", "-f", str(compose_path)]
        subprocess.run([*command, "up", "-d"], check=True)
        try:
            token = base64.b64encode(b"operator:phase9-example-password").decode()
            headers = {"Authorization": f"Basic {token}", "X-Forwarded-For": "203.0.113.7"}
            for _ in range(30):
                status, body = request(f"http://127.0.0.1:{port}/api/whoami", headers)
                if status == 200:
                    received = json.loads(body)
                    break
                time.sleep(1)
            else:
                raise RuntimeError("proxy chain did not become ready")
            if received.get("X-Forwarded-For") == "203.0.113.7":
                raise RuntimeError("Caddy accepted forged X-Forwarded-For")
            if "Authorization" in received:
                raise RuntimeError("Caddy forwarded Authorization upstream")
            status, _ = request(f"http://127.0.0.1:{port}/api/whoami", {})
            if status != 401:
                raise RuntimeError(f"expected unauthenticated 401, received {status}")
            direct_values = ("198.51.100.10", "198.51.100.11")
            for trusted_xff in direct_values:
                status, body = request(
                    f"http://127.0.0.1:{frontend_port}/api/whoami",
                    {"X-Forwarded-For": trusted_xff},
                )
                if status != 200 or json.loads(body).get("X-Forwarded-For") != trusted_xff:
                    raise RuntimeError("nginx changed trusted X-Forwarded-For")
            print(f"verified proxy boundary; upstream XFF={received.get('X-Forwarded-For')}; direct nginx XFF values preserved")
        finally:
            subprocess.run([*command, "down", "-v"], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
