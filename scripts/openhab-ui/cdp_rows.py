#!/usr/bin/env python3
"""Screenshot every top-level grid row of a page, one PNG each, at twice the pixels (the social-media shots, one per
row). Usage: cdp_rows.py URL OUT_PREFIX [WAIT_S] [WIDTH] [dark]   writes OUT_PREFIX-1.png, -2.png, ... from the top;
through ui_proxy.py with a DEMO_JSON (GERMAN=1 for homepi's own texts) for a past day. The viewport grows to the
page's length before the shots, as a capture beyond it resizes the page and ECharts restarts its animations."""
import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request

import websockets

URL, PREFIX = sys.argv[1], sys.argv[2]
WAIT = float(sys.argv[3]) if len(sys.argv) > 3 else 20
W = int(sys.argv[4]) if len(sys.argv) > 4 else 1600
DARK = len(sys.argv) > 5 and sys.argv[5] == "dark"
PORT = 9224
SCALE = 2
# a row of the page's own grid, not one nested in a card
ROWS = """JSON.stringify([...document.querySelectorAll('.row')].filter((r) => !r.parentElement.closest('.row'))
  .map((r) => { const b = r.getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; }))"""


async def main():
    chrome = subprocess.Popen(
        ["google-chrome", "--headless=new", "--disable-gpu", "--no-first-run",
         "--user-data-dir=./chrome-prof-rows", f"--window-size={W},1000",
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
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=200_000_000) as ws:
            msg_id = 0

            async def call(method, **params):
                nonlocal msg_id
                msg_id += 1
                await ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
                while True:
                    reply = json.loads(await ws.recv())
                    if reply.get("id") == msg_id:
                        return reply.get("result", reply)

            async def size(height):
                await call("Emulation.setDeviceMetricsOverride", width=W, height=height, deviceScaleFactor=SCALE,
                           mobile=False, screenWidth=W, screenHeight=height)

            await size(1000)
            await call("Emulation.setScrollbarsHidden", hidden=True)  # every page's rows as wide
            if DARK:
                await call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
            await call("Page.navigate", url=URL)
            await asyncio.sleep(WAIT)
            height = 1000
            for _ in range(4):
                # MainUI scrolls inside .page-content: grow the viewport to its content until it stops growing
                r = await call("Runtime.evaluate", returnByValue=True, expression=(
                    "Math.ceil(Math.max(document.documentElement.scrollHeight, ...[...document.querySelectorAll("
                    "'.page-content')].map((e) => e.scrollHeight)))"))
                need = int(r["result"]["value"])
                if need <= height:
                    break
                height = need
                await size(height)
                await asyncio.sleep(6)  # the charts drawn anew at the new size
            rows = json.loads((await call("Runtime.evaluate", expression=ROWS, returnByValue=True))["result"]["value"])
            for i, (x, y, w, h) in enumerate(rows, 1):
                shot = await call("Page.captureScreenshot", format="png", captureBeyondViewport=False,
                                  clip={"x": x, "y": y, "width": w, "height": h, "scale": 1})
                open(f"{PREFIX}-{i}.png", "wb").write(base64.b64decode(shot["data"]))
            print(len(rows), "rows")
    finally:
        chrome.terminate()


asyncio.run(main())
