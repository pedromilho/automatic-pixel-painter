"""A saída da interface encerra o servidor; recarregar não encerra."""

from http.server import ThreadingHTTPServer
from pathlib import Path
import json
import re
import sys
import threading
import time
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wplace_local import Session, make_handler


session = Session()
server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(session, "test-token"))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f"http://127.0.0.1:{server.server_address[1]}"


def opened_page():
    with urlopen(base + "/") as response:
        html = response.read().decode("utf-8")
    return re.search(r"const pageId = '([^']+)'", html).group(1)


def close_page(page_id):
    data = json.dumps({"token": "test-token", "page_id": page_id}).encode("utf-8")
    with urlopen(Request(base + "/api/ui-close", data=data,
                         headers={"Content-Type": "application/json"})) as response:
        return json.load(response)["closing"]


try:
    first = opened_page()
    assert close_page(first)
    time.sleep(0.5)
    second = opened_page()
    assert second != first
    assert not close_page(first)
    time.sleep(4.5)
    assert thread.is_alive(), "Recarregar a interface encerrou o servidor"
    assert close_page(second)
    thread.join(6)
    assert not thread.is_alive(), "Fechar a interface não encerrou o servidor"
    assert session.stop_event.is_set()
    print("OK: fechar encerra o servidor; recarregar mantém a interface")
finally:
    if thread.is_alive():
        server.shutdown()
    server.server_close()
