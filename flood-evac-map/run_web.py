"""
Start the evacuation map web server.

Run from the project root:
    python run_web.py
"""

import logging
import os
import sys
from pathlib import Path

if "GDAL_DATA" not in os.environ:
    for _candidate in [
        Path(sys.executable).parent / "Library" / "share" / "gdal",
        Path(sys.executable).parent.parent / "Library" / "share" / "gdal",
    ]:
        if _candidate.exists():
            os.environ["GDAL_DATA"] = str(_candidate)
            break

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

if __name__ == "__main__":
    print("=" * 60)
    print("Intelligent Evacuation System - Web Server")
    print("Open http://127.0.0.1:8000 in your browser")
    print("From your phone (same Wi-Fi): http://<YOUR-PC-IP>:8000")
    print("=" * 60)
    uvicorn.run("src.web.app:app", host="0.0.0.0", port=8000, reload=False)
