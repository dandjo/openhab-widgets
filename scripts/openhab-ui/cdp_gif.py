#!/usr/bin/env python3
"""Record one card of a MainUI page as an animated GIF. Usage: [PRE_JS=file.js] cdp_gif.py URL CARD_INDEX WIDTH OUT.gif SECONDS
[dark] [SCALE]; PRE_JS runs once the page has rendered, before the recording; with FPS the card's SVG
animations are paused and stepped at that rate, for even frames.
Frames are clipped screenshots taken as fast as Chrome delivers them; each frame lasts as long as it took, so the
animations keep their real speed. One palette for all frames, from the first, no dithering: flat card colours
stay flat and do not flicker between frames."""
import asyncio, base64, io, json, os, subprocess, sys, time, urllib.request
import websockets
import numpy as np
from PIL import Image

URL, INDEX, W, OUT, SECONDS = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], float(sys.argv[5])
DARK = len(sys.argv) > 6 and sys.argv[6] == "dark"
SCALE = float(sys.argv[7]) if len(sys.argv) > 7 else 1.0
PORT = 9241
PRE_JS = open(os.environ["PRE_JS"]).read() if os.environ.get("PRE_JS") else ""
FPS = float(os.environ.get("FPS", 0))  # step the SVG animations at this rate instead of recording in real time


async def main():
    chrome = subprocess.Popen(["google-chrome", "--headless=new", "--disable-gpu", "--no-first-run",
                               "--user-data-dir=./chrome-prof8", f"--window-size={W},1000",
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
                await call("Emulation.setDeviceMetricsOverride", width=W, height=h, deviceScaleFactor=SCALE,
                           mobile=W < 600, screenWidth=W, screenHeight=h)

            await metrics(1000)
            if DARK:
                await call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
            await call("Page.navigate", url=URL)
            await asyncio.sleep(14)
            ev = lambda js: call("Runtime.evaluate", expression=js, returnByValue=True)
            sh = (await ev("document.querySelector('.page-current .page-content').scrollHeight"))["result"]["value"]
            await metrics(int(sh) + 80)
            await asyncio.sleep(5)
            if PRE_JS:
                print("pre:", (await call("Runtime.evaluate", expression=PRE_JS, returnByValue=True,
                                          awaitPromise=True))["result"].get("value"))
                await asyncio.sleep(2)
            x, y, w, h = json.loads((await ev(f"""JSON.stringify((() => {{
                const r = document.querySelectorAll('.page-current .card')[{INDEX}].getBoundingClientRect();
                return [r.left, r.top, r.width, r.height]; }})())"""))["result"]["value"])
            m = 6
            clip = {"x": max(0, x - m), "y": max(0, y - m), "width": w + 2 * m, "height": h + 2 * m, "scale": 1}
            frames, stamps = [], []
            if FPS:
                # the drawings' animations are SMIL: pause every SVG timeline of the card and step it
                svgs = f"[...document.querySelectorAll('.page-current .card')[{INDEX}].querySelectorAll('svg')]"
                t0 = (await ev(f"(() => {{ const s = {svgs}; s.forEach(x => x.pauseAnimations()); "
                               "return s.length ? s[0].getCurrentTime() : 0; })()"))["result"]["value"]
                for k in range(round(SECONDS * FPS)):
                    await call("Runtime.evaluate", awaitPromise=True, expression=(
                        f"(() => {{ {svgs}.forEach(x => x.setCurrentTime({t0 + k / FPS})); "
                        "return new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); })()"))
                    shot = await call("Page.captureScreenshot", format="png", clip=clip)
                    frames.append(Image.open(io.BytesIO(base64.b64decode(shot["data"]))).convert("RGB"))
            else:
                t0 = time.monotonic()
                while time.monotonic() - t0 < SECONDS:
                    shot = await call("Page.captureScreenshot", format="png", clip=clip)
                    stamps.append(time.monotonic())
                    frames.append(Image.open(io.BytesIO(base64.b64decode(shot["data"]))).convert("RGB"))
    finally:
        chrome.terminate()
    if FPS:
        durations = [round(1000 / FPS)] * len(frames)
    else:
        durations = [max(20, round((b - a) * 1000)) for a, b in zip(stamps, stamps[1:])]
        durations.append(durations[-1] if durations else 100)
    # the most frequent exact colours of the first frame (card background, text, fills) as fixed entries, the rest
    # of the palette by median cut: nearest-colour mapping then keeps white white
    counts = sorted(frames[0].getcolors(maxcolors=1 << 24), reverse=True)
    fixed = [c for _, c in counts[:64]]
    cut = frames[0].quantize(colors=256 - len(fixed), method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    rest = cut.getpalette()[:3 * (256 - len(fixed))]
    pal = np.array(fixed + [tuple(rest[i:i + 3]) for i in range(0, len(rest), 3)], dtype=np.int32)
    gif = []
    for f in frames:  # every colour to its nearest palette entry, exactly (Pillow's own mapping is approximate)
        a = np.asarray(f, dtype=np.int32).reshape(-1, 3)
        colours, inverse = np.unique(a[:, 0] << 16 | a[:, 1] << 8 | a[:, 2], return_inverse=True)
        rgb = np.stack([colours >> 16, colours >> 8 & 255, colours & 255], axis=1)
        nearest = np.argmin(((rgb[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2), axis=1).astype(np.uint8)
        p = Image.fromarray(nearest[inverse.reshape(-1)].reshape(f.size[1], f.size[0]), "P")
        p.putpalette(pal.astype(np.uint8).flatten().tolist())
        gif.append(p)
    gif[0].save(OUT, save_all=True, append_images=gif[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(f"{OUT}: {len(frames)} frames, {sum(durations) / 1000:.1f} s, {round(sum(durations) / len(frames))} ms each")


asyncio.run(main())
