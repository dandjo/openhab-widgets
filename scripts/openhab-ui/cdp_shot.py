#!/usr/bin/env python3
"""Screenshot a URL after a fixed wait via Chrome DevTools. Usage: cdp_shot.py URL OUT.png [WAIT_S] [WIDTH] [HEIGHT]"""
import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request

import websockets

URL, OUT = sys.argv[1], sys.argv[2]
WAIT = float(sys.argv[3]) if len(sys.argv) > 3 else 15
W = int(sys.argv[4]) if len(sys.argv) > 4 else 1200
H = int(sys.argv[5]) if len(sys.argv) > 5 else 800
DARK = len(sys.argv) > 6 and sys.argv[6] == "dark"
PORT = 9223


async def main():
    chrome = subprocess.Popen(
        ["google-chrome", "--headless=new", "--disable-gpu", "--no-first-run",
         "--user-data-dir=./chrome-prof", f"--window-size={W},{H}",
         f"--remote-debugging-port={PORT}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list"))
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            msg_id = 0

            async def call(method, **params):
                nonlocal msg_id
                msg_id += 1
                await ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
                while True:
                    reply = json.loads(await ws.recv())
                    if reply.get("id") == msg_id:
                        return reply.get("result", reply)

            await call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=W < 600, screenWidth=W, screenHeight=H)
            if DARK:
                await call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
            await call("Page.navigate", url=URL)
            await asyncio.sleep(WAIT)
            shot = await call("Page.captureScreenshot", format="png")
            open(OUT, "wb").write(base64.b64decode(shot["data"]))
            print("saved", OUT)
    finally:
        chrome.terminate()


asyncio.run(main())
