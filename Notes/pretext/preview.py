#!/usr/bin/env python3
"""Rebuild on TeX changes and serve the PreTeXt HTML preview."""
import http.server
import subprocess
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTES = HERE.parent

def sources():
    return {p: p.stat().st_mtime_ns for p in NOTES.glob("Chap*/*.tex")}

def rebuild():
    subprocess.run(["python3", str(HERE / "build.py")], check=True)
    subprocess.run(["pretext", "build", "web"], cwd=HERE, check=True)

def watch():
    previous = sources()
    while True:
        time.sleep(2)
        current = sources()
        if current != previous:
            try:
                rebuild()
                print("PreTeXt preview updated", flush=True)
            except Exception as exc:
                print(f"PreTeXt rebuild failed: {exc}", flush=True)
            previous = current

if __name__ == "__main__":
    rebuild()
    threading.Thread(target=watch, daemon=True).start()
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(*args, directory=str(HERE / "output" / "web"), **kwargs)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        print(f"Preview: http://127.0.0.1:{server.server_port}/", flush=True)
        server.serve_forever()
