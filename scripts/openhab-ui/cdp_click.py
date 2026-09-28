#!/usr/bin/env python3
"""Load URL, wait, click at (x, y), wait, screenshot. Usage: cdp_click.py URL OUT X Y [W H dark]"""
import asyncio, base64, json, subprocess, sys, time, urllib.request
import websockets
URL, OUT, X, Y = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
W = int(sys.argv[5]) if len(sys.argv) > 5 else 1400
H = int(sys.argv[6]) if len(sys.argv) > 6 else 1200
DARK = len(sys.argv) > 7 and sys.argv[7] == "dark"
PORT = 9224
async def main():
    chrome = subprocess.Popen(["google-chrome", "--headless=new", "--disable-gpu", "--no-first-run",
                               "--user-data-dir=./chrome-prof2", f"--window-size={W},{H}",
                               f"--remote-debugging-port={PORT}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                page = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list")) if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            n = 0
            async def call(method, **params):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("id") == n:
                        return r.get("result", r)
            await call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False, screenWidth=W, screenHeight=H)
            if DARK:
                await call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
            await call("Page.navigate", url=URL)
            await asyncio.sleep(15)
            for t in ("mousePressed", "mouseReleased"):
                await call("Input.dispatchMouseEvent", type=t, x=X, y=Y, button="left", clickCount=1)
            await asyncio.sleep(2.5)
            shot = await call("Page.captureScreenshot", format="png")
            open(OUT, "wb").write(base64.b64decode(shot["data"]))
            print("saved", OUT)
    finally:
        chrome.terminate()
asyncio.run(main())
