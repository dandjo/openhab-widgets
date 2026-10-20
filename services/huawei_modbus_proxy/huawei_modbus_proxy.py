#!/usr/bin/env python3
"""A Modbus TCP proxy in front of a Huawei inverter's SDongle, so that several clients can share it.

The SDongle serves one Modbus TCP connection at a time: when a second client connects, it hands that client's answers
to the first one and then closes both connections. The proxy holds the only connection to the dongle and passes the
requests of any number of local clients to it, one at a time:
- each request goes out under a transaction id of the proxy's own; an answer under another id, the late answer to a
  request that timed out, is dropped. A client that took such an answer for the next request's would otherwise
  reset its connection (openHAB's Modbus binding logs a ModbusUnexpectedTransactionIdException);
- a request the dongle does not answer in time (ANSWER_TIMEOUT, a frame of a file FILE_ANSWER_TIMEOUT) gets the Modbus
  exception 0x0B (gateway target device failed to respond), one the proxy cannot send for want of a connection 0x0A
  (gateway path unavailable), so that the client tries again without resetting its connection; before the next
  request the proxy waits up to LATE_ANSWER_WAIT more for the late answer and drops it, as the dongle is still busy
  with it; after TIMEOUTS_BEFORE_RECONNECT timeouts in a row it connects anew;
- after connecting it waits SETTLE_AFTER_CONNECT, and between an answer and the next request at least
  GAP_BETWEEN_REQUESTS, as openHAB's Modbus binding does (afterConnectionDelayMillis, timeBetweenTransactionsMillis);
- the function codes do not matter, so Huawei's file transfer (0x41) passes as well. Its frames take the dongle 1 to
  4 s each against about 0.1 s for registers, so other clients' requests go between them: a client holding the dongle
  for a whole file would starve the others into timeouts, and the dongle keeps a file upload apart from register
  reads between its frames. But it knows one upload at a time, two at once spoil each other: another client's start
  of an upload (0x41 sub 0x05) waits until the running one is completed (sub 0x0C), its client gone, or
  UPLOAD_IDLE_LIMIT after its client's last request;
- nothing is cached and nothing is changed but the transaction id.
It logs connections, timeouts, dropped answers and, every REPORT_INTERVAL, the transactions with their mean and
longest time.

The settings come from the environment, HUAWEI_MODBUS_PROXY_<setting>, the README lists them; only DONGLE, the
dongle's host[:port], has no default. LISTEN is 127.0.0.1:5502 by default: keep it local, Modbus knows no
authentication.
"""
import asyncio
import collections
import os
import signal
import struct
import sys
import time

# Modbus TCP frames: the header (transaction id, protocol id 0, the length of what follows it, unit id), then the PDU
# (protocol data unit: the function code and its data)
HEADER = struct.Struct(">HHHB")
EXCEPTION_FLAG = 0x80
GATEWAY_PATH_UNAVAILABLE = 0x0A
GATEWAY_TARGET_FAILED = 0x0B
# Huawei's file transfer and the sub-functions that start and complete an upload
FILE_TRANSFER = 0x41
UPLOAD_START = 0x05
UPLOAD_COMPLETE = 0x0C


def address_setting(name, default_port, default_host=None):
    """(host, port) from HUAWEI_MODBUS_PROXY_<name>, given as host, host:port or [IPv6 address]:port"""
    value = os.environ.get(f"HUAWEI_MODBUS_PROXY_{name}", default_host)
    if not value:
        sys.exit(f"HUAWEI_MODBUS_PROXY_{name} is not set (host[:port])")
    if value.startswith("["):
        host, _, after_host = value[1:].partition("]")
        return host, int(after_host[1:]) if after_host.startswith(":") else default_port
    if value.count(":") == 1:
        host, port = value.split(":")
        return host, int(port)
    return value, default_port


def number_setting(name, default):
    """HUAWEI_MODBUS_PROXY_<name> as a number of the default's type"""
    return type(default)(os.environ.get(f"HUAWEI_MODBUS_PROXY_{name}", default))


LISTEN = address_setting("LISTEN", 5502, "127.0.0.1")
DONGLE = address_setting("DONGLE", 502)
SETTLE_AFTER_CONNECT = number_setting("SETTLE_AFTER_CONNECT", 0.8)  # s before the first request
# s for an answer: for some 15 s after a file upload the dongle answers registers only after about 3.5 s, which a
# limit of 3 s dropped, failing three tries of a client in a row
ANSWER_TIMEOUT = number_setting("ANSWER_TIMEOUT", 5.0)
FILE_ANSWER_TIMEOUT = number_setting("FILE_ANSWER_TIMEOUT", 8.0)  # s for an answer to a file transfer request
UPLOAD_IDLE_LIMIT = number_setting("UPLOAD_IDLE_LIMIT", 30.0)  # s without a request until an upload counts as given up
LATE_ANSWER_WAIT = number_setting("LATE_ANSWER_WAIT", 2.0)  # s more for the late answer to a request that timed out
GAP_BETWEEN_REQUESTS = number_setting("GAP_BETWEEN_REQUESTS", 0.5)  # s at least from an answer to the next request
RECONNECT_DELAY = number_setting("RECONNECT_DELAY", 5.0)  # s after a failed connection attempt
TIMEOUTS_BEFORE_RECONNECT = number_setting("TIMEOUTS_BEFORE_RECONNECT", 3)
REPORT_INTERVAL = number_setting("REPORT_INTERVAL", 3600)  # s between the statistics lines


def log(*args):
    print(*args, flush=True)


def exception_answer(pdu, code):
    """the Modbus exception answer to a request"""
    return bytes([pdu[0] | EXCEPTION_FLAG, code])


def frame(transaction_id, unit_id, pdu):
    return HEADER.pack(transaction_id, 0, len(pdu) + 1, unit_id) + pdu


class Request:
    """a client's request as it waits in the queue"""
    __slots__ = ("client", "transaction_id", "unit_id", "pdu")

    def __init__(self, client, transaction_id, unit_id, pdu):
        self.client, self.transaction_id, self.unit_id, self.pdu = client, transaction_id, unit_id, pdu

    def is_upload_start(self):
        return self.pdu[:2] == bytes([FILE_TRANSFER, UPLOAD_START])


class Client:
    def __init__(self, writer):
        host, port = writer.get_extra_info("peername")[:2]
        self.name = f"{host}:{port}"
        self.writer = writer
        self.connected = True

    def send_answer(self, transaction_id, unit_id, pdu):
        if self.connected:
            self.writer.write(frame(transaction_id, unit_id, pdu))


class Proxy:
    def __init__(self):
        self.queue = collections.deque()
        self.request_waiting = asyncio.Event()
        self.client_count = 0
        self.dongle_reader = self.dongle_writer = None
        self.transaction_id = 0  # the last one sent to the dongle
        self.next_connect_attempt = 0.0
        self.last_answer_at = 0.0
        self.timeouts_in_row = 0
        self.late_answer_deadline = 0.0  # while a late answer may still come
        self.late_request_sent_at = 0.0
        self.uploading_client = None  # the client whose file upload runs
        self.upload_deadline = 0.0  # its next request expected by then
        self.counters = collections.Counter()
        self.transaction_times = []

    # ------------------------------------------------------------ the clients

    async def serve_client(self, reader, writer):
        client = Client(writer)
        self.client_count += 1
        log(f"client {client.name} connected ({self.client_count} now)")
        try:
            while True:
                transaction_id, protocol, length, unit_id = HEADER.unpack(await reader.readexactly(HEADER.size))
                if protocol != 0 or not 2 <= length <= 254:
                    log(f"client {client.name}: no Modbus TCP (protocol {protocol}, length {length}), closed")
                    break
                pdu = await reader.readexactly(length - 1)
                self.queue.append(Request(client, transaction_id, unit_id, pdu))
                self.request_waiting.set()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            client.connected = False
            self.client_count -= 1
            self.queue = collections.deque(request for request in self.queue if request.client is not client)
            if self.uploading_client is client:
                self.uploading_client = None
                self.request_waiting.set()
            writer.close()
            log(f"client {client.name} gone ({self.client_count} left)")

    def next_request(self):
        """the oldest request, but not another client's start of a file upload while one runs"""
        if self.uploading_client and time.monotonic() > self.upload_deadline:
            log(f"file upload of client {self.uploading_client.name} given up after {UPLOAD_IDLE_LIMIT:g} s "
                f"without a request")
            self.uploading_client = None
        for position, request in enumerate(self.queue):
            if self.uploading_client in (None, request.client) or not request.is_upload_start():
                del self.queue[position]
                return request
        return None

    async def forward_requests(self):
        while True:
            request = self.next_request()
            if request is None:
                self.request_waiting.clear()
                # while an upload runs, wake up at its deadline to give it up
                wait = max(0.05, self.upload_deadline - time.monotonic()) if self.uploading_client else None
                try:
                    await asyncio.wait_for(self.request_waiting.wait(), wait)
                except TimeoutError:
                    pass
                continue
            answer = await self.ask_dongle(request.unit_id, request.pdu)
            self.track_upload(request, answer)
            request.client.send_answer(request.transaction_id, request.unit_id, answer)

    def track_upload(self, request, answer):
        """which client's file upload runs, from its start to its completion"""
        if request.pdu[0] != FILE_TRANSFER or len(request.pdu) < 2:
            return
        sub_function = request.pdu[1]
        if sub_function == UPLOAD_START and not answer[0] & EXCEPTION_FLAG:
            self.uploading_client = request.client
        elif sub_function == UPLOAD_COMPLETE and self.uploading_client is request.client:
            self.uploading_client = None
        if self.uploading_client is request.client:
            self.upload_deadline = time.monotonic() + UPLOAD_IDLE_LIMIT

    # ------------------------------------------------------------ the dongle

    async def connect_dongle(self):
        if self.dongle_writer:
            return True
        if time.monotonic() < self.next_connect_attempt:
            return False
        try:
            self.dongle_reader, self.dongle_writer = await asyncio.wait_for(asyncio.open_connection(*DONGLE), 5)
        except (OSError, TimeoutError) as error:
            self.next_connect_attempt = time.monotonic() + RECONNECT_DELAY
            self.counters["failed connection attempts"] += 1
            log(f"no connection to the dongle: {error or type(error).__name__}")
            return False
        self.counters["connections"] += 1
        log(f"connected to the dongle at {DONGLE[0]}:{DONGLE[1]}")
        await asyncio.sleep(SETTLE_AFTER_CONNECT)
        return True

    def disconnect_dongle(self, reason):
        if self.dongle_writer:
            log(f"connection to the dongle closed: {reason}")
            self.dongle_writer.close()
        self.dongle_reader = self.dongle_writer = None
        self.timeouts_in_row = 0
        self.late_answer_deadline = 0.0

    async def drop_late_answer(self):
        """the late answer to the request that timed out, awaited until late_answer_deadline and dropped"""
        try:
            time_left = self.late_answer_deadline - time.monotonic()
            header = await asyncio.wait_for(self.dongle_reader.readexactly(HEADER.size), time_left)
            transaction_id, protocol, length, _ = HEADER.unpack(header)
            if protocol != 0 or not 2 <= length <= 260:
                raise OSError(f"no Modbus TCP from the dongle (protocol {protocol}, length {length})")
            await asyncio.wait_for(self.dongle_reader.readexactly(length - 1), 1.0)
            self.counters["late answers dropped"] += 1
            log(f"dropped a late answer (transaction {transaction_id}) "
                f"{time.monotonic() - self.late_request_sent_at:.1f} s after its request")
        except TimeoutError:
            pass
        except (OSError, asyncio.IncompleteReadError) as error:
            self.counters["connection errors"] += 1
            self.disconnect_dongle(error or type(error).__name__)
        self.late_answer_deadline = 0.0
        self.last_answer_at = time.monotonic()

    async def ask_dongle(self, unit_id, pdu):
        """the dongle's answer to one request, a Modbus exception where there is none"""
        if self.dongle_writer and self.late_answer_deadline > time.monotonic():
            await self.drop_late_answer()
        if not await self.connect_dongle():
            return exception_answer(pdu, GATEWAY_PATH_UNAVAILABLE)
        await asyncio.sleep(max(0.0, self.last_answer_at + GAP_BETWEEN_REQUESTS - time.monotonic()))
        self.transaction_id = self.transaction_id % 0xFFFF + 1
        sent_at, header_read = time.monotonic(), False
        timeout = FILE_ANSWER_TIMEOUT if pdu[0] == FILE_TRANSFER else ANSWER_TIMEOUT
        try:
            self.dongle_writer.write(frame(self.transaction_id, unit_id, pdu))
            await self.dongle_writer.drain()
            while True:
                time_left = sent_at + timeout - time.monotonic()
                header = await asyncio.wait_for(self.dongle_reader.readexactly(HEADER.size), time_left)
                transaction_id, protocol, length, _ = HEADER.unpack(header)
                header_read = True
                if protocol != 0 or not 2 <= length <= 260:
                    self.counters["connection errors"] += 1
                    self.disconnect_dongle(f"no Modbus TCP from the dongle (protocol {protocol}, length {length})")
                    return exception_answer(pdu, GATEWAY_TARGET_FAILED)
                # the rest of an answer follows its header at once; a cut answer leaves the stream out of step
                answer = await asyncio.wait_for(self.dongle_reader.readexactly(length - 1), max(time_left, 1.0))
                header_read = False
                if transaction_id == self.transaction_id:
                    break
                self.counters["late answers dropped"] += 1
                log(f"dropped a late answer (transaction {transaction_id}, waiting for {self.transaction_id})")
        except TimeoutError:
            self.last_answer_at = time.monotonic()
            if header_read:
                self.counters["connection errors"] += 1
                self.disconnect_dongle("an answer cut off")
                return exception_answer(pdu, GATEWAY_TARGET_FAILED)
            self.counters["timeouts"] += 1
            self.timeouts_in_row += 1
            log(f"no answer within {timeout:g} s (function {pdu[0]:#04x}, transaction {self.transaction_id})")
            self.late_answer_deadline = self.last_answer_at + LATE_ANSWER_WAIT
            self.late_request_sent_at = sent_at
            if self.timeouts_in_row >= TIMEOUTS_BEFORE_RECONNECT:
                self.disconnect_dongle(f"{TIMEOUTS_BEFORE_RECONNECT} timeouts in a row")
            return exception_answer(pdu, GATEWAY_TARGET_FAILED)
        except (OSError, asyncio.IncompleteReadError) as error:
            self.last_answer_at = time.monotonic()
            self.counters["connection errors"] += 1
            self.disconnect_dongle(error or type(error).__name__)
            return exception_answer(pdu, GATEWAY_TARGET_FAILED)
        self.last_answer_at = time.monotonic()
        self.timeouts_in_row = 0
        self.transaction_times.append(self.last_answer_at - sent_at)
        return answer

    # ------------------------------------------------------------ the statistics

    def report_statistics(self, span):
        count = len(self.transaction_times)
        mean = sum(self.transaction_times) / count if count else 0.0
        longest = max(self.transaction_times, default=0)
        counters = "".join(f", {name} {value}" for name, value in sorted(self.counters.items()))
        log(f"{span}: {count} transactions, mean {mean * 1000:.0f} ms, longest {longest * 1000:.0f} ms" + counters)
        self.counters.clear()
        self.transaction_times.clear()

    async def report_regularly(self):
        while True:
            await asyncio.sleep(REPORT_INTERVAL)
            self.report_statistics("last hour")


async def main():
    proxy = Proxy()
    server = await asyncio.start_server(proxy.serve_client, *LISTEN)
    log(f"listening on {LISTEN[0]}:{LISTEN[1]} for the dongle at {DONGLE[0]}:{DONGLE[1]}")
    stop_requested = asyncio.Event()
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(signal_number, stop_requested.set)
    tasks = [asyncio.create_task(proxy.forward_requests()), asyncio.create_task(proxy.report_regularly())]
    stopping = asyncio.create_task(stop_requested.wait())
    done, _ = await asyncio.wait([stopping, *tasks], return_when=asyncio.FIRST_COMPLETED)
    server.close()
    proxy.disconnect_dongle("stopping")
    proxy.report_statistics("until stopped")
    for task in tasks:
        if task in done and task.exception():
            log(f"stopped by an error: {task.exception()!r}")
            sys.exit(1)
        task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
