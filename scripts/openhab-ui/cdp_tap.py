#!/usr/bin/env python3
"""Load a page, tap the link over the tile whose text contains TEXT, and save the popup it opens.
Usage: cdp_tap.py URL OUT TEXT [dark]"""
import asyncio, base64, json, subprocess, sys, time, urllib.request
import websockets
URL, OUT, TEXT = sys.argv[1], sys.argv[2], sys.argv[3]
DARK = len(sys.argv) > 4 and sys.argv[4] == "dark"
W, H, PORT = 1400, 1000, 9247


async def main():
    chrome = subprocess.Popen(["google-chrome", "--headless=new", "--disable-gpu", "--no-first-run",
                               "--user-data-dir=./chrome-prof11", f"--window-size={W},{H}",
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
            await call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False,
                       screenWidth=W, screenHeight=H)
            if DARK:
                await call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
            await call("Page.navigate", url=URL)
            await asyncio.sleep(14)
            js = """(() => { const t = %s; const links = [...document.querySelectorAll('.page-current a.link, .page-current .item-link')];
              const hit = links.find(a => { const tile = a.parentElement; return tile && tile.innerText.trim().includes(t); });
              if (!hit) return 'no tile ' + t; hit.scrollIntoView({block: 'center'}); hit.click(); return 'tapped'; })()""" % json.dumps(TEXT)
            r = await call("Runtime.evaluate", expression=js, returnByValue=True)
            print(r.get("result", {}).get("value"))
            await asyncio.sleep(5)
            box = (await call("Runtime.evaluate", returnByValue=True, expression="""JSON.stringify((() => {
              const p = document.querySelector('.popup.modal-in'); if (!p) return null;
              const r = p.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })())"""))["result"]["value"]
            box = json.loads(box)
            clip = {"clip": {"x": box[0], "y": box[1], "width": box[2], "height": box[3], "scale": 1}} if box else {}
            shot = await call("Page.captureScreenshot", format="png", **clip)
            open(OUT, "wb").write(base64.b64decode(shot["data"]))
    finally:
        chrome.terminate()
asyncio.run(main())
