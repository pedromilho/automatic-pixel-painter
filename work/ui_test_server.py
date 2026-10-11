"""Servidor local de teste com uma captura salva; não aciona o Wplace."""

from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot_blue_marble import auto_roi
from wplace_local import Session, make_handler

image = cv2.imread(str(Path(__file__).with_name("preview_new.png")))
assert image is not None
session = Session()
session._replan(image, auto_roi(image))
server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(session, "test-token"))
print(f"http://127.0.0.1:{server.server_address[1]}/", flush=True)
server.serve_forever()
