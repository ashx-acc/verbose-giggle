"""Capture real browser screenshots of the running dashboard for the report.

Usage (from the project root):

    python scripts/capture_screenshots.py

The script starts a temporary Uvicorn server, drives headless Chrome/Edge,
and writes PNGs to ``exports/screenshots``. No extra Python packages needed.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "exports" / "screenshots"
PORT = 8011
BASE_URL = f"http://127.0.0.1:{PORT}"

BROWSER_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


def find_browser() -> Path:
    for candidate in BROWSER_CANDIDATES:
        if candidate.exists():
            return candidate
    raise SystemExit("Chrome or Edge was not found. Install one to capture screenshots.")


def wait_for_server(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.5)
    raise SystemExit("The temporary server did not start in time.")


def capture(browser: Path, url: str, destination: Path, size: str) -> None:
    profile_dir = Path(tempfile.mkdtemp(prefix="crime-shot-"))
    command = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        f"--user-data-dir={profile_dir}",
        f"--window-size={size}",
        "--virtual-time-budget=6000",
        f"--screenshot={destination}",
        url,
    ]
    subprocess.run(command, check=True, timeout=180)
    if not destination.exists():
        raise SystemExit(f"Screenshot was not written: {destination}")


def trim_and_split(source: Path, prefix: str, slice_height: int = 1500) -> list[Path]:
    """Trim trailing blank space and split a tall screenshot into readable parts."""
    with Image.open(source) as image:
        image = image.convert("RGB")
        width, height = image.size

        # Find the last row that contains a non-near-white pixel.
        pixels = image.load()
        last_content = height - 1
        step = max(1, width // 80)
        while last_content > 0:
            row_has_content = False
            for x in range(0, width, step):
                r, g, b = pixels[x, last_content]
                if r < 248 or g < 248 or b < 248:
                    row_has_content = True
                    break
            if row_has_content:
                break
            last_content -= 1

        height = min(image.height, last_content + 40)
        paths: list[Path] = []
        index = 1
        top = 0
        while top < height:
            bottom = min(top + slice_height, height)
            crop = image.crop((0, top, width, bottom))
            path = OUTPUT_DIR / f"{prefix}_part{index}.png"
            crop.save(path, format="PNG", optimize=True)
            paths.append(path)
            index += 1
            top = bottom
        return paths


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    browser = find_browser()

    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        wait_for_server()
        pages = (
            ("dashboard_full.png", f"{BASE_URL}/", "1440,4600"),
            ("community_crud_full.png", f"{BASE_URL}/community", "1440,2300"),
            ("swagger_api_full.png", f"{BASE_URL}/docs", "1440,1800"),
        )
        for filename, url, size in pages:
            destination = OUTPUT_DIR / filename
            print(f"Capturing {url} -> {destination.name}")
            capture(browser, url, destination, size)

        for filename, prefix in (
            ("dashboard_full.png", "dashboard"),
            ("community_crud_full.png", "community_crud"),
            ("swagger_api_full.png", "swagger_api"),
        ):
            parts = trim_and_split(OUTPUT_DIR / filename, prefix)
            print(f"{filename}: {len(parts)} part(s)")
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover
            server.kill()


if __name__ == "__main__":
    main()
