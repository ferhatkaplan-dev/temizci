"""Temizci yerel web sunucusu (yalnızca 127.0.0.1)."""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import secrets
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import core

WEB_DIR = Path(__file__).resolve().parent / "web"
MAX_BODY = 2 * 1024 * 1024


class Service:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.items: list[core.Item] = []
        self.by_id: dict[str, core.Item] = {}
        self.phase = "idle"  # idle | scanning | ready | cleaning
        self.progress = {"done": 0, "total": len(core.COLLECTORS), "label": ""}
        self.error: str | None = None
        self.results: list[dict] = []
        self.scanned_at: float | None = None
        self.disk = core.disk_info()
        self.report = core.system_report()
        self.token = secrets.token_urlsafe(24)

    # -- durum ------------------------------------------------------------
    def state(self) -> dict:
        with self.lock:
            return {
                "phase": self.phase,
                "progress": dict(self.progress),
                "items": [item.to_dict() for item in self.items],
                "total_reclaimable": core.reclaimable_total(self.items),
                "error": self.error,
                "results": self.results,
                "scanned_at": self.scanned_at,
                "disk": self.disk,
                "report": self.report,
                "version": core.VERSION,
                "history": core.load_history(12),
                "categories": core.CATEGORIES,
                "risk_order": core.RISK_ORDER,
            }

    # -- tarama -----------------------------------------------------------
    def start_scan(self) -> bool:
        with self.lock:
            if self.phase in {"scanning", "cleaning"}:
                return False
            self.phase = "scanning"
            self.error = None
            self.results = []
            self.progress = {"done": 0, "total": len(core.COLLECTORS), "label": "Hazırlanıyor"}
        threading.Thread(target=self._scan_worker, daemon=True, name="temizci-scan").start()
        return True

    def _scan_worker(self) -> None:
        def progress(done: int, total: int, label: str) -> None:
            with self.lock:
                self.progress = {"done": done, "total": total, "label": label}

        try:
            items = core.scan_all(progress=progress)
            report = core.system_report()
            with self.lock:
                self.items = items
                self.by_id = {item.id: item for item in items}
                self.scanned_at = time.time()
                self.disk = report["disk"]
                self.report = report
                self.progress = {"done": len(core.COLLECTORS), "total": len(core.COLLECTORS), "label": "Tamamlandı"}
                self.phase = "ready"
        except Exception as exc:  # noqa: BLE001 - kullanıcıya gösterilir
            with self.lock:
                self.error = f"Tarama başarısız: {exc}"
                self.phase = "ready"

    # -- temizlik ---------------------------------------------------------
    def start_clean(self, ids: list[str], mode: str) -> tuple[bool, str | None]:
        if mode not in {"delete", "trash"}:
            return False, "Geçersiz silme modu"
        if not isinstance(ids, list) or not ids:
            return False, "Hiçbir öğe seçilmedi"
        if len(ids) > 500:
            return False, "Çok fazla öğe seçildi"
        with self.lock:
            if self.phase != "ready":
                return False, "Temizlik için önce tarama tamamlanmalı"
            selected = [self.by_id[i] for i in ids if i in self.by_id]
            if len(selected) != len(ids):
                return False, "Bilinmeyen öğe kimliği"
            snapshot = {item.id: item for item in selected}
            self.phase = "cleaning"
            self.error = None
            self.results = []
            self.progress = {"done": 0, "total": len(ids), "label": "Temizleniyor"}
        threading.Thread(
            target=self._clean_worker,
            args=(snapshot, ids, mode),
            daemon=True,
            name="temizci-clean",
        ).start()
        return True, None

    def _clean_worker(self, snapshot: dict[str, core.Item], ids: list[str], mode: str) -> None:
        try:
            results = core.clean_items(snapshot, ids, mode=mode)
        except Exception as exc:  # noqa: BLE001
            results = [
                {"id": ident, "title": snapshot[ident].title, "status": "error", "freed": 0, "error": str(exc)}
                for ident in ids
            ]
        total_freed = sum(r.get("freed", 0) for r in results)
        entry = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": mode,
            "freed": total_freed,
            "items": [
                {
                    "title": r.get("title"),
                    "status": r.get("status"),
                    "freed": r.get("freed", 0),
                }
                for r in results
            ],
        }
        core.append_history(entry)
        try:
            trash_items = core.collect_trash({})
        except Exception:  # noqa: BLE001 - çöp yenilemesi temizliği engellemesin
            trash_items = []
        with self.lock:
            self.results = results
            removed = {r["id"] for r in results if r.get("status") in {"deleted", "trashed"}}
            self.items = [item for item in self.items if item.id not in removed]
            # Çöp kutusu değişmiş olabilir; tam tarama yapmadan hafifçe yenile.
            self.items = [item for item in self.items if item.rule_id != "trash"]
            self.items.extend(trash_items)
            self.by_id = {item.id: item for item in self.items}
            self.disk = core.disk_info()
            self.phase = "ready"
            self.progress = {"done": len(ids), "total": len(ids), "label": "Tamamlandı"}

    # -- terminal ---------------------------------------------------------
    def open_terminal(self, command: str) -> tuple[bool, str | None]:
        allowed = {item.command for item in self.items if item.action == "command" and item.command}
        if command not in allowed:
            return False, "Bu komut bu taramaya ait değil"
        script = (
            f"{command}; printf '\\n\\nİşlem tamamlandı. Kapatmak için Enter\\n'; read -r"
        )
        terminals: list[tuple[str, list[str]]] = [
            ("foot", ["foot", "--title=Temizci", "-e", "bash", "-lc", script]),
            ("alacritty", ["alacritty", "-t", "Temizci", "-e", "bash", "-lc", script]),
            ("ghostty", ["ghostty", "-e", "bash", "-lc", script]),
            ("konsole", ["konsole", "-e", "bash", "-lc", script]),
            ("xterm", ["xterm", "-T", "Temizci", "-e", "bash", "-lc", script]),
            ("gnome-terminal", ["gnome-terminal", "--", "bash", "-lc", script]),
        ]
        if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
            return False, "Grafik oturumu bulunamadı"
        for binary, argv in terminals:
            if shutil.which(binary):
                try:
                    subprocess.Popen(
                        argv,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                        env=os.environ.copy(),
                    )
                    return True, None
                except OSError as exc:
                    return False, f"Terminal açılamadı: {exc}"
        return False, "Desteklenen bir terminal emülatörü bulunamadı"


SERVICE = Service()


class Handler(BaseHTTPRequestHandler):
    server_version = f"Temizci/{core.VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # sessiz sunucu
        return

    # -- yardımcılar ------------------------------------------------------
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY:
            return None
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _check_token(self) -> bool:
        supplied = self.headers.get("X-Temizci-Token", "")
        return bool(supplied) and hmac.compare_digest(supplied, SERVICE.token)

    def _serve_file(self, relative: str) -> None:
        path = (WEB_DIR / relative).resolve()
        if WEB_DIR.resolve() not in path.parents or not path.is_file():
            self._error(404, "Bulunamadı")
            return
        if relative == "index.html":
            text = path.read_text(encoding="utf-8")
            text = text.replace("{{TOKEN}}", SERVICE.token).replace("{{VERSION}}", core.VERSION)
            self._send(200, text.encode("utf-8"), "text/html; charset=utf-8")
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self._send(200, path.read_bytes(), content_type)

    # -- yönlendirme ------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route in {"/", "/index.html"}:
            self._serve_file("index.html")
            return
        if route.startswith("/static/"):
            self._serve_file(route.removeprefix("/static/"))
            return
        if route == "/api/state":
            self._json(200, {"ok": True, **SERVICE.state()})
            return
        if route == "/api/health":
            self._json(200, {"ok": True, "version": core.VERSION})
            return
        self._error(404, "Bulunamadı")

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if not self._check_token():
            self._error(403, "Geçersiz oturum anahtarı. Sayfayı yenileyin.")
            return

        if route == "/api/scan":
            started = SERVICE.start_scan()
            if not started:
                self._error(409, "Tarama veya temizlik zaten sürüyor")
                return
            self._json(200, {"ok": True})
            return

        if route == "/api/clean":
            data = self._read_json()
            if data is None:
                self._error(400, "Geçersiz istek gövdesi")
                return
            if data.get("confirm") is not True:
                self._error(400, "Onay gerekli")
                return
            ids = data.get("ids")
            mode = data.get("mode", "delete")
            if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                self._error(400, "Geçersiz öğe listesi")
                return
            started, message = SERVICE.start_clean(ids, mode)
            if not started:
                self._error(409, message or "Temizlik başlatılamadı")
                return
            self._json(200, {"ok": True})
            return

        if route == "/api/terminal":
            data = self._read_json()
            if data is None or not isinstance(data.get("command"), str):
                self._error(400, "Geçersiz istek")
                return
            started, message = SERVICE.open_terminal(data["command"])
            if not started:
                self._error(400, message or "Terminal açılamadı")
                return
            self._json(200, {"ok": True})
            return

        self._error(404, "Bulunamadı")


def _pick_port(host: str, preferred: int) -> int:
    import socket

    for port in [preferred, 0]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return sock.getsockname()[1]
            except OSError:
                continue
    raise OSError("Boş port bulunamadı")


def run(port: int = 8765, open_browser: bool = True, host: str = "127.0.0.1") -> None:
    actual_port = _pick_port(host, port)
    server = ThreadingHTTPServer((host, actual_port), Handler)
    server.daemon_threads = True
    url = f"http://{host}:{actual_port}/"
    print(f"Temizci {core.VERSION} → {url}")
    print("Kapatmak için Ctrl+C")
    if open_browser:
        def launch() -> None:
            time.sleep(0.5)
            try:
                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=launch, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\nKapatılıyor…")
    finally:
        server.server_close()
