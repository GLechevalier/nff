"""OAuth authentication helpers — browser flow, callback server, direct login."""

import queue
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse, quote

import requests


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str
    expires_in: int = 3600


def percent_encode(s: str) -> str:
    return quote(s, safe="")


def open_browser(url: str) -> None:
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/C", "start", "", url])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url])
    else:
        subprocess.Popen(["xdg-open", url])


def bind_callback_server() -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(1)
    return sock, port


def _parse_callback(raw: bytes) -> TokenResponse:
    text = raw.decode("utf-8", errors="replace")
    # Extract the GET request line: "GET /callback?access_token=...&... HTTP/1.1"
    first_line = text.splitlines()[0] if text else ""
    path = first_line.split(" ")[1] if " " in first_line else ""
    params = parse_qs(urlparse(path).query)
    access = params.get("access_token", [""])[0]
    refresh = params.get("refresh_token", [""])[0]
    return TokenResponse(access_token=access, refresh_token=refresh)


def wait_for_callback(listener: socket.socket, timeout_secs: int) -> TokenResponse:
    result_q: queue.Queue = queue.Queue()

    def _accept():
        try:
            conn, _ = listener.accept()
            data = conn.recv(4096)
            conn.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nAuthenticated! You may close this tab."
            )
            conn.close()
            result_q.put(("ok", data))
        except Exception as exc:
            result_q.put(("err", exc))
        finally:
            listener.close()

    t = threading.Thread(target=_accept, daemon=True)
    t.start()

    try:
        kind, payload = result_q.get(timeout=timeout_secs)
    except queue.Empty:
        raise TimeoutError("OAuth callback timed out")

    if kind == "err":
        raise RuntimeError(f"Callback server error: {payload}")
    return _parse_callback(payload)


def direct_login(server_url: str, email: str, password: str) -> TokenResponse:
    resp = requests.post(
        f"{server_url}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return TokenResponse(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_in=data.get("expires_in", 3600),
    )


def refresh_tokens(server_url: str, refresh_token: str) -> TokenResponse:
    resp = requests.post(
        f"{server_url}/api/auth/refresh",
        json={"refresh_token": refresh_token},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return TokenResponse(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_in=data.get("expires_in", 3600),
    )
