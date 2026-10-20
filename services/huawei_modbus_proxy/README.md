# huawei_modbus_proxy

A small Modbus TCP proxy that lets several clients share the SDongle of a Huawei inverter.

The SDongle accepts only one Modbus TCP connection at a time. When a second client connects, the dongle hands that
client's answers to the first one and then drops both connections. So if openHAB polls the inverter and another
program wants to read it too (for example the optimizers' data, which Huawei only offers as a file transfer), they
cannot both talk to the dongle. The proxy solves this: it keeps the only connection to the dongle and serves any
number of local clients, passing their requests on one at a time.

## How it works

- **One request at a time, with its own transaction ids.** The proxy sends every request under a transaction id of
  its own and maps the answer back to the client's id. A late answer, which arrives after its request already timed
  out, is recognised by its id and dropped, so no client ever mistakes it for the answer to its next request.
- **Timeouts the client can handle.** If the dongle does not answer within 5 seconds (8 seconds for a frame of a file
  transfer), the client gets the Modbus exception 0x0B, "gateway target device failed to respond". Without a
  connection to the dongle it gets 0x0A, "gateway path unavailable". Either way the client simply tries again and
  keeps its connection. After three timeouts in a row the proxy reconnects to the dongle.
- **Gentle pacing.** It waits 0.8 seconds after connecting and leaves at least 0.5 seconds between an answer and the
  next request, as openHAB's Modbus binding does.
- **File transfers welcome.** Every function code passes, including Huawei's file transfer (0x41). A file comes in
  frames that take the dongle 1 to 4 seconds each, so other clients' requests are slipped in between the frames
  instead of waiting for the whole file. The dongle can handle only one upload at a time, though, so a second
  client's upload waits until the first one is completed, its client disconnects or it has been idle for 30 seconds.
- **Transparent.** Nothing is cached and nothing is changed except the transaction id; writes pass as they are.
- **Local only.** It listens on 127.0.0.1 by default, since Modbus has no authentication.

The dongle is slow after a file upload: for about 15 seconds it answers register reads only after about 3.5 seconds.
That is why the answer timeout is 5 seconds and not less.

## Requirements

Python 3.11 or later. Only the standard library is used.

## Installing

```
sudo mkdir -p /opt/huawei_modbus_proxy
sudo cp huawei_modbus_proxy.py README.md /opt/huawei_modbus_proxy/
python3 -m venv ~/.venv/huawei_modbus_proxy
install -m 600 env.example ~/.venv/huawei_modbus_proxy/.env
```

Set the dongle's address in `~/.venv/huawei_modbus_proxy/.env`. Then install the systemd unit, adjusting the user and
the paths in it:

```
sudo cp huawei-modbus-proxy.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now huawei-modbus-proxy
```

The unit reads the `.env` as its `EnvironmentFile`, starts the proxy before openHAB and restarts it if it stops.

## Settings

The proxy reads its settings from environment variables. Only the dongle's address is required.

| Variable | Default | Meaning |
| --- | --- | --- |
| `HUAWEI_MODBUS_PROXY_DONGLE` | (required) | the dongle's address as `host` or `host:port`; the port defaults to 502 |
| `HUAWEI_MODBUS_PROXY_LISTEN` | `127.0.0.1:5502` | where the clients connect |
| `HUAWEI_MODBUS_PROXY_ANSWER_TIMEOUT` | `5.0` | seconds to wait for the dongle's answer |
| `HUAWEI_MODBUS_PROXY_FILE_ANSWER_TIMEOUT` | `8.0` | seconds to wait for the answer to a file transfer request |
| `HUAWEI_MODBUS_PROXY_LATE_ANSWER_WAIT` | `2.0` | seconds to wait for a late answer before the next request goes out |
| `HUAWEI_MODBUS_PROXY_TIMEOUTS_BEFORE_RECONNECT` | `3` | timeouts in a row after which the proxy reconnects |
| `HUAWEI_MODBUS_PROXY_SETTLE_AFTER_CONNECT` | `0.8` | seconds to wait after connecting before the first request |
| `HUAWEI_MODBUS_PROXY_GAP_BETWEEN_REQUESTS` | `0.5` | minimum seconds between an answer and the next request |
| `HUAWEI_MODBUS_PROXY_UPLOAD_IDLE_LIMIT` | `30.0` | seconds without a request after which a client's file upload counts as abandoned |
| `HUAWEI_MODBUS_PROXY_RECONNECT_DELAY` | `5.0` | seconds between failed connection attempts |
| `HUAWEI_MODBUS_PROXY_REPORT_INTERVAL` | `3600` | seconds between the statistics lines in the log |

## Connecting openHAB

Point openHAB's Modbus TCP bridge at the proxy instead of the dongle, and give it a longer receive timeout, since a
request may have to wait behind a frame of another client's file transfer:

```
Bridge modbus:tcp:huawei_inverter [ host="127.0.0.1", port=5502, id=1, receiveTimeoutMillis=15000 ]
```

Other clients connect the same way. The rule
[`huawei_optimizers.js`](../../scripts/openhab-ui/applied/huawei_optimizers.js) in this repository is one: it reads
the optimizers' data with Huawei's file transfer through the proxy.

Never let a client talk to the dongle directly while the proxy runs.

## Logs

`journalctl -u huawei-modbus-proxy` shows clients connecting and leaving, the connections to the dongle, every
timeout and dropped late answer, and every hour a line with the number of transactions, their mean and longest time
and the counts of timeouts, dropped answers and connection errors.

## Removing it

Point the clients back at the dongle (openHAB's bridge with the dongle's host and port 502; a receive timeout of 3
seconds is enough then), make sure only one of them is left, and run
`sudo systemctl disable --now huawei-modbus-proxy`.
