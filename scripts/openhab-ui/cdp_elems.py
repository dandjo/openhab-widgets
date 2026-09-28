#!/usr/bin/env python3
"""Screenshot elements of a MainUI page at 2x. Usage: cdp_elems.py URL WIDTH OUTDIR RECTS_JS [PRE_JS] [dark]
RECTS_JS returns JSON [[name, x, y, w, h], ...] in page coordinates; each becomes OUTDIR/name.png, with a margin of
6 px. PRE_JS runs first (and may return a promise), e.g. to fold out details."""
import asyncio, base64, json, os, subprocess, sys, time, urllib.request
import websockets
URL, W, OUT, RECTS = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
PRE_JS = sys.argv[5] if len(sys.argv) > 5 else ""
DARK = len(sys.argv) > 6 and sys.argv[6] == "dark"
PORT = 9245


async def main():
    chrome = subprocess.Popen(["google-chrome", "--headless=new", "--disable-gpu", "--no-first-run",
                               "--user-data-dir=./chrome-prof10", f"--window-size={W},1000",
                               f"--remote-debugging-port={PORT}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                page = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list")) if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=100_000_000) as ws:
            n = 0

            async def call(method, **params):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("id") == n:
                        return r.get("result", r)

            async def metrics(h):
                await call("Emulation.setDeviceMetricsOverride", width=W, height=h, deviceScaleFactor=2, mobile=W < 600,
                           screenWidth=W, screenHeight=h)

            ev = lambda js: call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
            await metrics(1000)
            if DARK:
                await call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
            await call("Page.navigate", url=URL)
            await asyncio.sleep(14)
            if PRE_JS:
                print("pre:", (await ev(PRE_JS))["result"].get("value"))
                await asyncio.sleep(2)
            sh = (await ev("document.querySelector('.page-current .page-content').scrollHeight"))["result"]["value"]
            await metrics(int(sh) + 80)
            await asyncio.sleep(4)
            os.makedirs(OUT, exist_ok=True)
            for name, x, y, w, h in json.loads((await ev(RECTS))["result"]["value"]):
                m = 6
                shot = await call("Page.captureScreenshot", format="png", clip={
                    "x": max(0, x - m), "y": max(0, y - m), "width": w + 2 * m, "height": h + 2 * m, "scale": 1})
                open(os.path.join(OUT, name + ".png"), "wb").write(base64.b64decode(shot["data"]))
                print(os.path.join(OUT, name + ".png"))
    finally:
        chrome.terminate()
asyncio.run(main())
