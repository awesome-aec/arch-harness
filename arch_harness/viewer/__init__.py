"""Live viewer: a local three.js page (no build step) and a small JSON API over the model.

GET /              the page; GET /vendor/three/... three.js (THREE_VERSION, MIT) shipped in the repo, so the page runs offline
GET /api/version   a hash of model.json and the latest round; the page polls it and reloads the model on change
GET /api/model     solids (mm), elements failing the latest round, status
GET /film          a replay of rounds already run (film.html), from a film JSON written by `arch_harness film`
GET /api/film      that film JSON
POST /api/select   the element the architect clicked, kept in .arch-harness/selection.json: the seam for steering
                   the agent at it (e.g. pi's SDK steer()) in a later milestone
"""
from __future__ import annotations

import hashlib
import http.server
import json
import pathlib

from ..model import solids
from ..project import MODEL_DIR

THREE_VERSION = "0.170.0"
PAGE = pathlib.Path(__file__).with_name("index.html")
FILM_PAGE = pathlib.Path(__file__).with_name("film.html")
VENDOR = pathlib.Path(__file__).with_name("vendor")


def _latest_round(project: pathlib.Path):
    rounds = sorted((project / MODEL_DIR / "rounds").glob("round-*.json"))
    return json.loads(rounds[-1].read_text()) if rounds else None


def _version(project: pathlib.Path) -> str:
    h = hashlib.sha256()
    for p in [project / MODEL_DIR / "model.json"] + sorted((project / MODEL_DIR / "rounds").glob("round-*.json"))[-1:]:
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def model_payload(project: pathlib.Path) -> dict:
    model_path = project / MODEL_DIR / "model.json"
    if not model_path.exists():
        return {"project": None, "solids": [], "failing": [], "status": None, "site": None}
    model = json.loads(model_path.read_text())
    last = _latest_round(project)
    failing = sorted({f["element"] for f in last["failures"]}) if last else []
    status = ({"round": last["round"], "passed": last["passed"], "by_kind": last["by_kind"],
               "failures": last["failures"][:50]} if last else None)
    return {"project": model["project"]["name"], "site": model["site"], "building": model["building"],
            "storeys": model["storeys"], "solids": solids(model), "failing": failing, "status": status,
            "version": _version(project)}


def make_server(project, port: int, host: str = "127.0.0.1", film=None) -> http.server.ThreadingHTTPServer:
    project = pathlib.Path(project).resolve()
    film = pathlib.Path(film).resolve() if film else None

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, body: bytes, ctype: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]  # a page may carry a query (e.g. /film?capture=1)
            if path in ("/", "/index.html"):
                self._send(PAGE.read_text().replace("{{THREE_VERSION}}", THREE_VERSION).encode(), "text/html; charset=utf-8")
            elif path in ("/film", "/film.html") and film:
                self._send(FILM_PAGE.read_text().encode(), "text/html; charset=utf-8")
            elif path == "/api/film" and film:
                self._send(film.read_bytes(), "application/json")
            elif path.startswith("/vendor/"):
                f = (VENDOR / path[len("/vendor/"):]).resolve()
                if f.is_relative_to(VENDOR.resolve()) and f.is_file():
                    self._send(f.read_bytes(), "text/javascript" if f.suffix == ".js" else "text/plain; charset=utf-8")
                else:
                    self._send(b"not found", "text/plain", 404)
            elif path == "/api/version":
                self._send(json.dumps({"version": _version(project)}).encode(), "application/json")
            elif path == "/api/model":
                self._send(json.dumps(model_payload(project)).encode(), "application/json")
            else:
                self._send(b"not found", "text/plain", 404)

        def do_POST(self):
            if self.path != "/api/select":
                return self._send(b"not found", "text/plain", 404)
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            out = project / ".arch-harness" / "selection.json"
            out.parent.mkdir(exist_ok=True)
            out.write_text(json.dumps({"id": str(data.get("id", ""))}))
            self._send(b"{}", "application/json")

        def log_message(self, *args):  # quiet
            pass

    return http.server.ThreadingHTTPServer((host, port), Handler)


def serve_viewer(project, port: int = 8765, film=None):
    server = make_server(project, port, film=film)
    page = "film" if film else ""
    print(f"arch-harness viewer: http://127.0.0.1:{server.server_address[1]}/{page}  (project {project})", flush=True)
    server.serve_forever()
