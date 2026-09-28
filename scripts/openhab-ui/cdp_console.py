import asyncio, json, subprocess, sys, time, urllib.request
import websockets
URL = sys.argv[1]; PORT = 9230
async def main():
    chrome = subprocess.Popen(["google-chrome", "--headless=new", "--disable-gpu", "--no-first-run", "--user-data-dir=./chrome-prof4",
                               "--window-size=1400,1000", f"--remote-debugging-port={PORT}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                page = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list")) if t["type"] == "page"); break
            except Exception: time.sleep(0.2)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            n = 0
            async def send(m, **p):
                nonlocal n; n += 1
                await ws.send(json.dumps({"id": n, "method": m, "params": p}))
            await send("Runtime.enable"); await send("Log.enable")
            await send("Page.navigate", url=URL)
            end = time.time() + 16
            while time.time() < end:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1))
                except asyncio.TimeoutError:
                    continue
                if msg.get("method") == "Runtime.consoleAPICalled" and msg["params"]["type"] in ("error", "warning"):
                    print("CONSOLE", msg["params"]["type"], " ".join(str(a.get("value", a.get("description", "")))[:200] for a in msg["params"]["args"]))
                if msg.get("method") == "Runtime.exceptionThrown":
                    print("EXCEPTION", msg["params"]["exceptionDetails"].get("exception", {}).get("description", "")[:300])
    finally:
        chrome.terminate()
asyncio.run(main())
