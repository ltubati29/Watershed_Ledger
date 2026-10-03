#!/usr/bin/env python3
"""Local server for Watershed Ledger.

Run:  python3 server.py      then open  http://localhost:8000

It serves the dashboard and, when you press "Refresh from USGS", runs
fetch_usgs_to_ledger.collect() in the background, saves data/readings.csv, appends
data/history.json, and hands the new readings to the page. Only runs on your computer.
"""
import json
import re
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import fetch_usgs_to_ledger as usgs

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PORT = 8000
LOCK = threading.Lock()
HISTORY_LIMIT = 3000


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def save_history(rows, fetched, folder=DATA):
    path = folder / "history.json"
    try:
        hist = json.loads(path.read_text())
    except Exception:
        hist = []
    last = {h["order"]: h.get("observed") for h in hist}
    for r in rows:
        if r.get("observed") and last.get(r["order"]) == r["observed"]:
            continue  # same sensor reading as last time: do not duplicate it
        hist.append({"t": fetched, "name": r["name"], "order": r["order"],
                     "observed": r.get("observed", ""),
                     "r": {k: num(r.get(k)) for k in usgs.COLS}})
    path.write_text(json.dumps(hist[-HISTORY_LIMIT:]))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def local_only(self):
        return self.headers.get("Host", "").split(":")[0] in ("localhost", "127.0.0.1")

    def do_GET(self):
        path = self.path.split("?")[0]
        if not self.local_only():
            return self.send_error(403)
        if path == "/api/ping":
            return self.reply(200, {"ok": True})
        if path in ("/", "/index.html") or path.startswith("/data/"):
            return super().do_GET()
        self.send_error(404)

    def find(self, body):
        try:
            box = [float(x) for x in body.get("bbox", [])]
            assert len(box) == 4 and -180 <= box[0] < box[2] <= 180 and -90 <= box[1] < box[3] <= 90
        except (TypeError, ValueError, AssertionError):
            return self.reply(400, {"error": "Search area must be west, south, east, north."})
        try:
            self.reply(200, {"stations": usgs.find(tuple(box))})
        except Exception as e:
            self.reply(502, {"error": str(e)})

    def do_POST(self):
        if self.path not in ("/api/refresh", "/api/find") or self.headers.get("X-Ledger") != "1" or not self.local_only():
            return self.send_error(403)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self.reply(400, {"error": "Bad request."})
        if self.path == "/api/find":
            return self.find(body)
        sites = [str(s) for s in body.get("sites", []) if re.fullmatch(r"(USGS-)?\d{8,15}", str(s))][:12]
        sites = sites or usgs.DEFAULT_SITES
        if not LOCK.acquire(blocking=False):
            return self.reply(429, {"error": "A refresh is already running."})
        try:
            rows, warnings = usgs.collect(sites)
            if not rows:
                return self.reply(502, {"error": "USGS returned nothing. " + "; ".join(warnings)})
            DATA.mkdir(exist_ok=True)
            csv = usgs.to_csv(rows)
            (DATA / "readings.csv").write_text(csv)
            fetched = datetime.now(timezone.utc).isoformat()
            save_history(rows, fetched)
            self.reply(200, {"csv": csv, "fetched": fetched, "count": len(rows), "warnings": warnings})
        except Exception as e:
            self.reply(502, {"error": str(e)})
        finally:
            LOCK.release()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Watershed Ledger running at http://localhost:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
