"""Interface local para o assistente de pixels. Execute: python pixel_server.py"""

from __future__ import annotations

import argparse
import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time
from urllib.parse import urlparse

import cv2
import pyautogui
import pygetwindow

from pixel_detector import (
    TIMINGS,
    Timing,
    active_canvas_window,
    annotated,
    auto_roi,
    capture_bgr,
    detect_squares,
    locate_picker_in_screen,
    palette_top,
    paint,
    palette_open,
)


ROOT = Path(__file__).resolve().parent


def timing_for(speed: int, mode: str) -> Timing:
    """Nível 1 prioriza pausas; nível 10 prioriza velocidade."""
    if not 1 <= speed <= 10:
        raise ValueError("Velocidade precisa estar entre 1 e 10")
    fraction = (speed - 1) / 9
    if mode == "specific":
        interval = 0.60 * (0.04 / 0.60) ** fraction
        movement = 0.08 * (1 - fraction)
        return Timing(0, movement, 0.02, 0, interval, 0.01, 0)
    if mode != "per_pixel":
        raise ValueError("Modo desconhecido")
    base = TIMINGS["fast"]
    factor = 2.2 - 1.85 * fraction
    return Timing(
        max(0.04, base.activation * factor),
        max(0, base.movement * factor),
        max(0.04, base.hover * factor),
        max(0.08, base.sample * factor),
        max(0.02, base.between * factor),
        0.02,
        max(0.05, base.key_hold * factor),
    )


class Session:
    def __init__(self):
        self.lock = threading.RLock()
        self.image = None
        self.roi = None
        self.default_roi = None
        self.max_y = 0
        self.squares = []
        self.pitch = (None, None)
        self.picker = None
        self.preview_png = b""
        self.window_handle = None
        self.window_title = ""
        self.version = 0
        self.running = False
        self.completed = 0
        self.total = 0
        self.cursor = 0
        self.message = "Capture o mapa para começar."
        self.stop_event = threading.Event()

    def _replan(self, image, roi):
        height, width = image.shape[:2]
        x1, y1, x2, y2 = map(int, roi)
        bar_top = palette_top(image)
        bottom = bar_top - 6 if bar_top is not None else height - 6
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= bottom):
            raise ValueError("Selecione uma área do mapa acima da paleta")
        squares, pitch = detect_squares(image, (x1, y1, x2, y2))
        try:
            picker = locate_picker_in_screen(image)
        except RuntimeError:
            picker = None
        point = None if picker is None else (picker[0], picker[1])
        success, encoded = cv2.imencode(".png", annotated(image, (x1, y1, x2, y2), squares, point))
        if not success:
            raise RuntimeError("Não foi possível gerar a prévia")
        with self.lock:
            self.image = image
            self.roi = (x1, y1, x2, y2)
            self.max_y = bottom
            self.squares = squares
            self.pitch = pitch
            self.picker = picker
            self.preview_png = encoded.tobytes()
            self.version += 1
            self.cursor = 0
            self.message = f"{len(squares)} quadradinhos detectados. Confira a prévia."
            return self.plan()

    def plan(self):
        with self.lock:
            return {
                "ready": self.image is not None,
                "count": len(self.squares),
                "cursor": self.cursor,
                "pitch": self.pitch,
                "picker": self.picker,
                "roi": self.roi,
                "auto_roi": self.default_roi,
                "max_y": self.max_y,
                "version": self.version,
                "width": 0 if self.image is None else self.image.shape[1],
                "height": 0 if self.image is None else self.image.shape[0],
                "message": self.message,
            }

    def capture(self, window_title="", bounds=None):
        with self.lock:
            if self.running:
                raise ValueError("Interrompa a pintura antes de capturar novamente")
        if not isinstance(window_title, str) or len(window_title) > 100:
            raise ValueError("Informe até 100 caracteres do título da janela")
        ui_window = pygetwindow.getActiveWindow()
        target = None
        try:
            target = active_canvas_window(window_title)
            image = capture_bgr()
            if not palette_open(image):
                raise RuntimeError("Abra o modo de pintura e deixe a paleta visível no mapa")
            roi = auto_roi(image)
            default_roi = roi
            if bounds is not None:
                if (not isinstance(bounds, list) or len(bounds) not in (2, 4) or
                        any(not isinstance(value, (int, float)) or not math.isfinite(value) or
                            value < 0 or value > 1 for value in bounds)):
                    raise ValueError("Ajuste de área inválido")
                width = image.shape[1]
                bottom = roi[3]
                if len(bounds) == 2:
                    x1, y1 = roi[:2]
                    x2 = round(width * bounds[0])
                    y2 = round(bottom * bounds[1])
                else:
                    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
                        raise ValueError("Ajuste de área inválido")
                    x1 = min(width - 10, round(width * bounds[0]))
                    y1 = min(bottom - 10, round(bottom * bounds[1]))
                    x2 = round(width * bounds[2])
                    y2 = round(bottom * bounds[3])
                roi = (x1, y1, max(x1 + 10, min(width, x2)),
                       max(y1 + 10, min(bottom, y2)))
            with self.lock:
                self.default_roi = default_roi
            result = self._replan(image, roi)
            with self.lock:
                self.window_handle = target._hWnd
                self.window_title = window_title
            return result
        finally:
            if ui_window is not None and (target is None or ui_window._hWnd != target._hWnd):
                try:
                    ui_window.activate()
                except Exception:
                    pass

    def update_roi(self, roi):
        with self.lock:
            if self.running:
                raise ValueError("Interrompa a pintura antes de mudar a área")
            image = self.image
        if image is None:
            raise ValueError("Capture o mapa primeiro")
        if not isinstance(roi, list) or len(roi) != 4:
            raise ValueError("Área inválida")
        return self._replan(image, roi)

    def start(self, mode, speed, limit, version):
        if mode not in ("per_pixel", "specific"):
            raise ValueError("Escolha um modo de pintura")
        speed = int(speed)
        timing = timing_for(speed, mode)
        with self.lock:
            if self.running:
                raise ValueError("Já existe uma pintura em andamento")
            if self.image is None or not self.squares:
                raise ValueError("Capture e confira uma prévia antes de começar")
            if mode == "per_pixel" and self.picker is None:
                raise ValueError("Não localizei o color picker na captura. Reabra a paleta e capture novamente")
            if int(version) != self.version:
                raise ValueError("A prévia mudou; atualize a página antes de iniciar")
            requested = int(limit)
            if requested < 1:
                raise ValueError("O limite deve ser positivo")
            if self.cursor >= len(self.squares):
                raise ValueError("Todos os quadradinhos da prévia já foram usados; capture novamente")
            start_cursor = self.cursor
            squares = self.squares[start_cursor:start_cursor + requested]
            window_handle = self.window_handle
            window_title = self.window_title
            self.total = len(squares)
            self.completed = 0
            self.running = True
            self.message = "Preparando a pintura..."
            self.stop_event.clear()

        def worker():
            try:
                def progress(done, total):
                    with self.lock:
                        self.completed = done
                        self.total = total
                        self.cursor = start_cursor + done
                        self.message = f"Marcados {done} de {total} pixels."

                done = paint(
                    squares, len(squares), timing, "button",
                    ROOT / "apos_conta_gotas.png" if mode == "per_pixel" else None,
                    mode=mode, on_progress=progress, stop_event=self.stop_event,
                    window_title=window_title, window_handle=window_handle,
                )
                with self.lock:
                    self.completed = done
                    self.cursor = start_cursor + done
                    if self.stop_event.is_set():
                        self.message = f"Interrompido após {done} pixels. Revise o lote."
                    else:
                        self.message = f"{done} pixels marcados. Confira o resultado no mapa."
            except pyautogui.FailSafeException:
                with self.lock:
                    self.message = "Interrompido pelo cursor no canto da tela."
            except Exception as exc:
                with self.lock:
                    self.message = f"Pintura interrompida: {exc}"
            finally:
                with self.lock:
                    self.running = False

        threading.Thread(target=worker, name="pintura-pixels", daemon=True).start()
        return self.status()

    def stop(self):
        self.stop_event.set()
        with self.lock:
            if self.running:
                self.message = "Parando após o pixel atual..."
            return self.status()

    def status(self):
        with self.lock:
            return {
                "running": self.running,
                "completed": self.completed,
                "total": self.total,
                "cursor": self.cursor,
                "remaining": len(self.squares) - self.cursor,
                "message": self.message,
            }


def make_handler(session: Session, token: str):
    close_lock = threading.Lock()
    close_timer = None
    active_page_id = None

    def page_opened():
        nonlocal close_timer, active_page_id
        page_id = secrets.token_urlsafe(12)
        with close_lock:
            if close_timer is not None:
                close_timer.cancel()
                close_timer = None
            active_page_id = page_id
        return page_id

    def close_after_grace(server, page_id):
        with close_lock:
            if page_id != active_page_id:
                return
        session.stop_event.set()
        server.shutdown()

    def schedule_close(server, page_id):
        nonlocal close_timer
        with close_lock:
            if page_id != active_page_id:
                return False
            if close_timer is not None:
                close_timer.cancel()
            # Recarregar a página também dispara pagehide. Uma nova abertura
            # cancela este timer; fechar a janela deixa o servidor encerrar.
            close_timer = threading.Timer(4.0, close_after_grace, args=(server, page_id))
            close_timer.daemon = True
            close_timer.start()
            return True

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send_bytes(self, status, data, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, status, payload):
            self.send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                page_id = page_opened()
                html = (ROOT / "pixel_ui.html").read_text(encoding="utf-8")
                html = html.replace("__TOKEN__", token).replace("__PAGE_ID__", page_id)
                self.send_bytes(200, html.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/preview":
                with session.lock:
                    data = session.preview_png
                if data:
                    self.send_bytes(200, data, "image/png")
                else:
                    self.send_json(404, {"error": "Capture o mapa primeiro"})
            elif path == "/api/plan":
                self.send_json(200, session.plan())
            elif path == "/api/status":
                self.send_json(200, session.status())
            else:
                self.send_json(404, {"error": "Não encontrado"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/ui-close":
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    self.send_json(400, {"error": "Pedido inválido"})
                    return
                try:
                    body = json.loads(self.rfile.read(length))
                except (ValueError, TypeError):
                    self.send_json(400, {"error": "Pedido inválido"})
                    return
                if not isinstance(body, dict) or body.get("token") != token:
                    self.send_json(403, {"error": "Acesso negado"})
                    return
                closing = schedule_close(self.server, body.get("page_id"))
                self.send_json(200, {"closing": closing})
                return
            if self.headers.get("X-Local-Token") != token:
                self.send_json(403, {"error": "Acesso negado"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 16384:
                    raise ValueError("Pedido muito grande")
                body = json.loads(self.rfile.read(length) or b"{}")
                if path == "/api/capture":
                    result = session.capture(bounds=body.get("bounds"))
                elif path == "/api/roi":
                    result = session.update_roi(body.get("roi"))
                elif path == "/api/start":
                    result = session.start(body.get("mode"), body.get("speed"), body.get("limit"), body.get("version"))
                elif path == "/api/stop":
                    result = session.stop()
                else:
                    self.send_json(404, {"error": "Não encontrado"})
                    return
                self.send_json(200, result)
            except (ValueError, TypeError, RuntimeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_json(500, {"error": f"Falha: {exc}"})

    return Handler


def watch_interface_window(server, session: Session, previous_handles: set[int]):
    """Encerra o servidor quando a janela do Edge criada para o bot fecha."""
    deadline = time.monotonic() + 30
    handle = None
    while time.monotonic() < deadline:
        windows = pygetwindow.getWindowsWithTitle("Assistente de Pixels")
        new_windows = [win for win in windows if win._hWnd not in previous_handles]
        if new_windows:
            handle = new_windows[-1]._hWnd
            break
        time.sleep(0.3)
    if handle is None:
        return  # O sinal pagehide da interface continua disponível.
    while ctypes.windll.user32.IsWindow(handle):
        time.sleep(0.4)
    session.stop_event.set()
    server.shutdown()


def edge_path() -> Path | None:
    candidates = [
        shutil.which("msedge.exe"),
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="Não abrir a janela do navegador automaticamente")
    args = parser.parse_args()
    session = Session()
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(session, token))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Assistente de Pixels: {url}", flush=True)
    if not args.no_browser:
        edge = edge_path()
        if edge:
            previous_handles = {win._hWnd for win in pygetwindow.getWindowsWithTitle("Assistente de Pixels")}
            subprocess.Popen([str(edge), f"--app={url}", "--new-window"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            threading.Thread(target=watch_interface_window,
                             args=(server, session, previous_handles),
                             name="janela-interface", daemon=True).start()
        else:
            print("Abra o endereço acima em uma janela separada do mapa.", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        session.stop_event.set()
        deadline = time.monotonic() + 3
        while session.running and time.monotonic() < deadline:
            time.sleep(0.05)
        server.server_close()


if __name__ == "__main__":
    main()
