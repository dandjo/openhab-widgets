#!/usr/bin/env python3
"""Load URL, wait, evaluate a JS expression, print the JSON result. Usage: cdp_eval.py URL WAIT 'JS'"""
import asyncio, json, subprocess, sys, time, urllib.request
import websockets
URL, WAIT, JS = sys.argv[1], float(sys.argv[2]), sys.argv[3]
W = int(sys.argv[4]) if len(sys.argv) > 4 else 1400
PORT = 9227
async def main():
    chrome = subprocess.Popen(["google-chrome", "--headless=new", "--disable-gpu", "--no-first-run", "--user-data-dir=./chrome-prof4",
                               f"--window-size={W},900", f"--remote-debugging-port={PORT}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                page = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list")) if t["type"] == "page"); break
            except Exception: time.sleep(0.2)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            n = 0
            async def call(m, **p):
                nonlocal n; n += 1
                await ws.send(json.dumps({"id": n, "method": m, "params": p}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("id") == n: return r.get("result", r)
            await call("Emulation.setDeviceMetricsOverride", width=W, height=900, deviceScaleFactor=1, mobile=False, screenWidth=W, screenHeight=900)
            await call("Page.navigate", url=URL)
            await asyncio.sleep(WAIT)
            r = await call("Runtime.evaluate", expression=JS, returnByValue=True)
            print(json.dumps(r.get("result", {}).get("value"), indent=1))
    finally:
        chrome.terminate()
asyncio.run(main())
