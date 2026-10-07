#!/usr/bin/env python3
"""The English MainUI for the repository's screenshots, without touching openHAB: a local proxy in front of the tunnel
that hands the browser every widget and page translated by i18n/en.py, the items with the English labels and option
texts they had before the German ones (i18n/labels_export.json), state events with those option texts, and an English
locale; everything else passes through unchanged, server-sent events streamed.
With DEMO_JSON (demo_day.py's output) the browser sees a past moment instead, so no screenshot shows the day's
counters just reset: its clock set back to it (charts load that day) and every persisted item's state at it in the
items and the state events; the weather page stays live, its forecast looks ahead.
Usage: ui_proxy.py ITEMS_JSON [PORT] [UPSTREAM] [DEMO_JSON]   (defaults 18081 and http://127.0.0.1:18080)"""
import http.client
import json
import os
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "i18n"))
import en  # noqa: E402

en.load_item_labels(sys.argv[1])
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18081
UP = urllib.parse.urlparse(sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:18080")
DEMO = json.load(open(sys.argv[4])) if len(sys.argv) > 4 else None
LIVE_PAGES = ("/page/weather",)
# MainUI's clock set back to the demo's moment, before any of its scripts runs
CLOCK_JS = """<script>(() => {
  const shift = %d - Date.now(), Real = Date;
  function Shifted(...a) {
    if (!(this instanceof Shifted)) return new Real(Real.now() + shift).toString();
    return a.length ? new Real(...a) : new Real(Real.now() + shift);
  }
  Shifted.prototype = Real.prototype;
  Shifted.now = () => Real.now() + shift; Shifted.parse = Real.parse; Shifted.UTC = Real.UTC;
  window.Date = Shifted;
})();</script>"""
EXPORT = json.load(open(os.path.join(HERE, "i18n", "labels_export.json")))
LABELS = {name: e["label"] for name, e in EXPORT["items"].items() if e.get("label")}


def options(text):
    return dict(part.split("=", 1) for part in re.split(r"[,;]", text or "") if "=" in part)


# the English texts of state and command options, by item and value
OPTIONS = {}
for key, md in EXPORT["metadata"].items():
    kind, _, item = key.partition(":")
    if kind in ("stateDescription", "commandDescription") and md.get("config", {}).get("options"):
        OPTIONS.setdefault(item, {}).update(options(md["config"]["options"]))
TEXT_STATES = ("_active_program", "_program_phase")
HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-connection"}


def demo_item(item):
    """An item as it was at the demo's moment: its state, its formatted state for MainUI's display."""
    s = DEMO["states"].get(item.get("name"))
    if s:
        item["state"] = s["state"]
        if "transformedState" in item:
            item["transformedState"] = s.get("displayState", s["state"])
    for member in item.get("members", []) or []:
        demo_item(member)
    return item


def english_item(item):
    name = item.get("name")
    if name in LABELS:
        item["label"] = LABELS[name]
    elif item.get("label"):
        item["label"] = en.tr_core(item["label"])
    opts = OPTIONS.get(name, {})
    for desc, key in (("stateDescription", "options"), ("commandDescription", "commandOptions")):
        for o in (item.get(desc) or {}).get(key, []) or []:
            v = o.get("value", o.get("command"))
            if v in opts:
                o["label"] = opts[v]
            elif o.get("label"):
                o["label"] = en.tr_core(o["label"])
    st = item.get("state")
    if st in opts and "transformedState" in item:
        item["transformedState"] = opts[st]
    if name and name.endswith(TEXT_STATES) and isinstance(st, str):
        item["state"] = en.tr_core(st)
    for member in item.get("members", []) or []:
        english_item(member)
    return item


GERMAN_NUMBER = re.compile(r"^(-?\d{1,3}(?:\.\d{3})+|-?\d+)(,\d+)?(\s.*)?$")


WEEKDAYS = {"Mo": "Mon", "Di": "Tue", "Mi": "Wed", "Do": "Thu", "Fr": "Fri", "Sa": "Sat", "So": "Sun"}


def english_date(text):
    """A date as openHAB formats it for de_AT with a weekday, Mo. 12:00, as Mon 12:00."""
    m = re.match(r"^(Mo|Di|Mi|Do|Fr|Sa|So)\.(\s)", text)
    return WEEKDAYS[m.group(1)] + text[3:] if m else text


def english_number(text):
    """A number as openHAB formats it for de_AT, 1.234,5 kWh, as en_GB writes it, 1,234.5 kWh; other texts as they are."""
    m = GERMAN_NUMBER.match(text)
    if not m or not (m.group(2) or "." in m.group(1)):
        return text
    return m.group(1).replace(".", ",") + (m.group(2) or "").replace(",", ".") + (m.group(3) or "")


def english_states(payload):
    """A state event: {item: {state, displayState, ...}}: the display text from the English options, numbers written
    the English way, and for a text state an English display text where the table knows one (the state stays)."""
    for name, s in payload.items():
        if isinstance(s, dict):
            opts = OPTIONS.get(name, {})
            if s.get("state") in opts:
                s["displayState"] = opts[s["state"]]
            elif isinstance(s.get("displayState"), str):
                s["displayState"] = english_date(english_number(en.tr_core(s["displayState"])))
            elif isinstance(s.get("state"), str) and en.tr_core(s["state"]) != s["state"]:
                s["displayState"] = en.tr_core(s["state"])
            # a Miele machine's program and phase are shown as their state and compared nowhere
            if name.endswith(TEXT_STATES) and isinstance(s.get("state"), str):
                s["state"] = en.tr_core(s["state"])
    return payload


def rest_path(path):
    """The path as MainUI means it: it asks for ui%3Awidget as often as for ui:widget."""
    return urllib.parse.unquote(urllib.parse.urlparse(path).path).rstrip("/")


def rewrite(path, body, demo=False):
    p = rest_path(path)
    data = json.loads(body)
    if demo and p.startswith("/rest/items"):
        data = [demo_item(i) for i in data] if isinstance(data, list) else demo_item(data)
    if p == "/rest":
        data["locale"] = "en_GB"
    elif p.startswith("/rest/ui/components/ui:"):
        if isinstance(data, list):
            data = [en.translate(v) for v in data]
        else:
            data = en.translate(data)
    elif p.startswith("/rest/items"):
        data = [english_item(i) for i in data] if isinstance(data, list) else english_item(data)
    return json.dumps(data, ensure_ascii=False).encode()


def rewritten(path):
    p = rest_path(path)
    return p == "/rest" or p.startswith("/rest/ui/components/ui:") or p.startswith("/rest/items")


class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def relay(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP and k.lower() != "host"}
        # the demo for every request but a live page's own and those it makes (its referer)
        page = urllib.parse.urlparse(self.headers.get("Referer") or "").path if self.path.startswith("/rest") else self.path
        demo = DEMO is not None and not page.startswith(LIVE_PAGES)
        # MainUI's service worker would hand out its cached index.html, without the clock: none registers, and one
        # a browser profile already has is dropped at its next update check
        if DEMO is not None and urllib.parse.urlparse(self.path).path in ("/registerSW.js", "/sw.js"):
            data = b"" if self.path.startswith("/registerSW.js") else b"not while showing a past moment"
            self.send_response(200 if data == b"" else 404)
            self.send_header("Content-Type", "application/javascript" if data == b"" else "text/plain")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if rewritten(self.path) or demo:
            headers["Accept-Encoding"] = "identity"
        conn = http.client.HTTPConnection(UP.hostname, UP.port, timeout=600)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            r = conn.getresponse()
            ctype = r.getheader("Content-Type", "")
            if "text/event-stream" in ctype:
                self.send_response(r.status)
                for k, v in r.getheaders():
                    if k.lower() not in HOP and k.lower() != "content-length":
                        self.send_header(k, v)
                self.end_headers()
                while True:
                    line = r.readline()
                    if not line:
                        break
                    if line.startswith(b"data:"):
                        try:
                            payload = json.loads(line[5:].decode())
                            if isinstance(payload, dict) and demo:
                                payload = {k: dict(DEMO["states"].get(k, v)) for k, v in payload.items()}
                            if isinstance(payload, dict):
                                line = b"data: " + json.dumps(english_states(payload), ensure_ascii=False).encode() + b"\n"
                        except ValueError:
                            pass
                    self.wfile.write(line)
                    self.wfile.flush()
                return
            data = r.read()
            if r.status == 200 and rewritten(self.path) and "json" in ctype:
                try:
                    data = rewrite(self.path, data, demo)
                except ValueError:
                    pass
            elif r.status == 200 and demo and "text/html" in ctype and b"<head>" in data:
                data = data.replace(b"<head>", b"<head>" + (CLOCK_JS % DEMO["time_ms"]).encode(), 1)
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in HOP and k.lower() != "content-length":
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            conn.close()

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_OPTIONS = relay


ThreadingHTTPServer.daemon_threads = True
ThreadingHTTPServer(("127.0.0.1", PORT), Proxy).serve_forever()
