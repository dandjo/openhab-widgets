#!/usr/bin/env python3
"""Screenshot every card of a MainUI page on its own. Usage: cdp_cards.py URL OUTPREFIX WIDTH [dark]
The viewport grows to the page's full height first, so cards below the fold render and can be clipped."""
import asyncio, base64, json, re, subprocess, sys, time, urllib.request
import websockets
URL, OUT, W = sys.argv[1], sys.argv[2], int(sys.argv[3])
DARK = len(sys.argv) > 4 and sys.argv[4] == "dark"
PRE_JS = sys.argv[5] if len(sys.argv) > 5 else ""
PORT = 9235


async def main():
    chrome = subprocess.Popen(["google-chrome", "--headless=new", "--disable-gpu", "--no-first-run",
                               "--user-data-dir=./chrome-prof7", f"--window-size={W},1000",
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

            await metrics(1000)
            if DARK:
                await call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
            await call("Page.navigate", url=URL)
            await asyncio.sleep(14)
            ev = lambda js: call("Runtime.evaluate", expression=js, returnByValue=True)
            if PRE_JS:
                print("pre js:", (await ev(PRE_JS))["result"].get("value"))
                await asyncio.sleep(3)
            sh = (await ev("document.querySelector('.page-current .page-content').scrollHeight"))["result"]["value"]
            await metrics(int(sh) + 80)
            await asyncio.sleep(5)
            cards = (await ev("""JSON.stringify([...document.querySelectorAll('.page-current .card')].map(c => {
                const r = c.getBoundingClientRect(); return [r.left, r.top, r.width, r.height,
                ((c.querySelector('.card-header') || {}).innerText || 'card').split('·')[0].trim()]; }))"""))["result"]["value"]
            for i, (x, y, w, h, title) in enumerate(json.loads(cards)):
                slug = re.sub(r"[^a-z0-9]+", "-", title.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")).strip("-")
                m = 6
                shot = await call("Page.captureScreenshot", format="png",
                                  clip={"x": max(0, x - m), "y": max(0, y - m), "width": w + 2 * m, "height": h + 2 * m, "scale": 1})
                open(f"{OUT}-{i}-{slug}.png", "wb").write(base64.b64decode(shot["data"]))
                print(f"{OUT}-{i}-{slug}.png")
            full = await call("Page.captureScreenshot", format="png")
            open(f"{OUT}-full.png", "wb").write(base64.b64decode(full["data"]))
    finally:
        chrome.terminate()
asyncio.run(main())
