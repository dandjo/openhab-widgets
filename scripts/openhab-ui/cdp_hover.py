import asyncio, base64, json, subprocess, sys, time, urllib.request
import websockets
URL = sys.argv[1]; PORT = 9226
HOVERS = [(float(a), float(b), out, [float(v) for v in clip.split(",")]) for a, b, out, clip in
          (h.split(":") for h in sys.argv[2:])]
async def main():
    chrome = subprocess.Popen(["google-chrome", "--headless=new", "--disable-gpu", "--no-first-run", "--user-data-dir=./chrome-prof5",
                               "--window-size=1400,3300", f"--remote-debugging-port={PORT}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                page = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list")) if t["type"] == "page"); break
            except Exception: time.sleep(0.2)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=80_000_000) as ws:
            n = 0
            async def call(m, **p):
                nonlocal n; n += 1
                await ws.send(json.dumps({"id": n, "method": m, "params": p}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("id") == n: return r.get("result", r)
            await call("Emulation.setDeviceMetricsOverride", width=1400, height=3300, deviceScaleFactor=1, mobile=False)
            await call("Page.navigate", url=URL)
            await asyncio.sleep(20)
            for x, y, out, (cx, cy, cw, ch) in HOVERS:
                await call("Input.dispatchMouseEvent", type="mouseMoved", x=x - 5, y=y)
                await call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
                await asyncio.sleep(1.5)
                shot = await call("Page.captureScreenshot", format="png", clip={"x": cx, "y": cy, "width": cw, "height": ch, "scale": 1})
                open(out, "wb").write(base64.b64decode(shot["data"])); print("saved", out)
    finally:
        chrome.terminate()
asyncio.run(main())
