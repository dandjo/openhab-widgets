# huawei_modbus_proxy

A Modbus TCP proxy in front of the Huawei inverter's SDongle (on homepi since 2026-10-20). The dongle serves one
Modbus TCP connection at a time. A second client beside openHAB got its answer delivered to openHAB, and then the dongle
closed both connections. The proxy holds the only connection to the dongle and passes the requests of any number of
local clients to it, one at a time. Its clients on homepi: openHAB's Modbus bridge `modbus:tcp:huawei_inverter`, and
the rule `huawei_optimizers`
([`scripts/openhab-ui/applied/huawei_optimizers.js`](../../scripts/openhab-ui/applied/huawei_optimizers.js) in the
widgets repository), which reads the optimizers' readings with Huawei's file transfer.

## What it does

- **One request at a time, with its own transaction ids.** An answer under another id, the late answer to a request
  that timed out, is dropped. openHAB's bridge used to take such an answer for the next request's: it logged a
  `ModbusUnexpectedTransactionIdException` and reset the connection after most timeouts.
- **Timeouts.** A request the dongle does not answer within 5 s (a frame of a file within 8 s) gets the Modbus
  exception 0x0B (gateway target device failed to respond). 5 s, not less: for some 15 s after a file upload the
  dongle answers register reads only after about 3.5 s. Without a connection to the dongle a request gets 0x0A
  (gateway path unavailable). The client then tries again without resetting its connection. Before the next request
  the proxy waits up to 2 s more for the late answer and drops it, since the dongle is still busy with it. After 3
  timeouts in a row it connects anew.
- **Pacing as openHAB's bridge did it.** It waits 0.8 s after connecting, and at least 0.5 s between an answer and the
  next request.
- **Any function code.** Huawei's file transfer (0x41) passes as well. Its frames take the dongle 1 to 4 s each,
  against about 0.1 s for registers, so other clients' requests go between them. A client that held the dongle for a
  whole file starved openHAB's bridge into timeouts, and the dongle keeps an upload apart from register reads between
  its frames. But it knows one upload at a time, and two at once spoil each other. So another client's start of an
  upload (0x41 sub 0x05) waits in the queue until the running upload is completed (sub 0x0C), its client gone, or 30 s
  after its client's last request.
- **Nothing cached, nothing changed** but the transaction id. Writes (the battery's forcible charge) pass unchanged.
- **Local only.** It listens on 127.0.0.1 by default, since Modbus knows no authentication.

## Settings

From the environment; on homepi from the venv's `.env`, which the systemd unit reads as its `EnvironmentFile`
([`env.example`](env.example) shows the format). The times are the ones described above.

| Variable | Default | Meaning |
| --- | --- | --- |
| `HUAWEI_MODBUS_PROXY_DONGLE` | (required) | the dongle's `host[:port]`, port 502 if left out |
| `HUAWEI_MODBUS_PROXY_LISTEN` | `127.0.0.1:5502` | where the clients connect, `host:port` |
| `HUAWEI_MODBUS_PROXY_ANSWER_TIMEOUT` | `5.0` | s for the dongle's answer to a request |
| `HUAWEI_MODBUS_PROXY_FILE_ANSWER_TIMEOUT` | `8.0` | s for its answer to a file transfer request (0x41) |
| `HUAWEI_MODBUS_PROXY_LATE_ANSWER_WAIT` | `2.0` | s more for the late answer to a request that timed out |
| `HUAWEI_MODBUS_PROXY_TIMEOUTS_BEFORE_RECONNECT` | `3` | timeouts in a row after which it connects anew |
| `HUAWEI_MODBUS_PROXY_SETTLE_AFTER_CONNECT` | `0.8` | s after connecting before the first request |
| `HUAWEI_MODBUS_PROXY_GAP_BETWEEN_REQUESTS` | `0.5` | s at least between an answer and the next request |
| `HUAWEI_MODBUS_PROXY_UPLOAD_IDLE_LIMIT` | `30.0` | s without a request after which a client's file upload counts as given up |
| `HUAWEI_MODBUS_PROXY_RECONNECT_DELAY` | `5.0` | s after a failed connection attempt before the next |
| `HUAWEI_MODBUS_PROXY_REPORT_INTERVAL` | `3600` | s between the statistics lines |

## Installing

The standard library is enough (Python 3.11 or later).

```
sudo mkdir -p /opt/huawei_modbus_proxy
sudo cp huawei_modbus_proxy.py README.md env.example huawei-modbus-proxy.service /opt/huawei_modbus_proxy/
python3 -m venv ~/.venv/huawei_modbus_proxy
install -m 600 env.example ~/.venv/huawei_modbus_proxy/.env   # then set the dongle's address in it
sudo cp huawei-modbus-proxy.service /etc/systemd/system/      # adjust User and the paths
sudo systemctl daemon-reload && sudo systemctl enable --now huawei-modbus-proxy
```

Then point the Modbus clients at the proxy instead of the dongle. openHAB's bridge needs a longer receive timeout
(`receiveTimeoutMillis` 15000), as a request may wait behind a frame of a file.

## Layout on homepi

| Path | What |
| --- | --- |
| `/opt/huawei_modbus_proxy/huawei_modbus_proxy.py` | the proxy (root's, like all of `/opt`: changes with sudo) |
| `/opt/huawei_modbus_proxy/huawei-modbus-proxy.service` | a copy of the unit, as published |
| `/home/pi/.venv/huawei_modbus_proxy` | its venv, the standard library only |
| `/home/pi/.venv/huawei_modbus_proxy/.env` | its settings (mode 600) |
| `/etc/systemd/system/huawei-modbus-proxy.service` | the service, as `pi`, restarted 5 s after it stops; before openHAB at boot |

## Logs

`journalctl -u huawei-modbus-proxy` shows the following:

- clients coming and going;
- connections to the dongle;
- every timeout and dropped late answer;
- every hour a line with the transactions, their mean and longest time, and the counts of timeouts, dropped answers
  and connection errors.

## Going back

To connect openHAB to the dongle directly again:

1. Disable the rule `huawei_optimizers`; it reaches the dongle only through the proxy.
2. Set the bridge's host and port back to the dongle's (`HUAWEI_MODBUS_PROXY_DONGLE`) and `receiveTimeoutMillis` to
   3000.
3. Then run `sudo systemctl disable --now huawei-modbus-proxy`.

Never let the proxy and a direct client talk to the dongle at the same time.
