#!/usr/bin/env python3
"""Finish a history write from its backup CSV (measurement,time_ns,old,new): write the new values of the given
measurements, in batches, against the local InfluxDB. Writing a value that is already there changes nothing.
Usage: hp_split_finish.py BACKUP.csv.gz MEASUREMENT..."""
import csv
import gzip
import sys
import time
import urllib.parse
import urllib.request

URL = "http://127.0.0.1:8086/write?" + urllib.parse.urlencode({"db": "openhab", "precision": "ns"})
wanted = set(sys.argv[2:])
batch, total = [], 0


def flush():
    global batch, total
    if batch:
        req = urllib.request.Request(URL, data="\n".join(batch).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=300) as resp:
            assert resp.status == 204, resp.status
        total += len(batch)
        batch = []
        time.sleep(0.3)


with gzip.open(sys.argv[1], "rt") as f:
    for row in csv.DictReader(f):
        m = row["measurement"]
        if m in wanted:
            batch.append(f"{m},item={m} value={float(row['new'])!r} {row['time_ns']}")
            if len(batch) >= 10000:
                flush()
                if total % 200000 == 0:
                    print(time.strftime("%H:%M:%S"), total, "points", flush=True)
flush()
print(time.strftime("%H:%M:%S"), "done,", total, "points", flush=True)
