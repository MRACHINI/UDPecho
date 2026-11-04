"""UDPecho - a tiny, safe UDP echo server for measuring packet loss and latency of game-like UDP traffic.

It answers ONLY datagrams that start with a magic prefix (default "NESTPROBE1|"), so it cannot be abused
to reflect or amplify traffic towards third parties: replies are never larger than the request and are
sent only to the sender of a correctly prefixed probe.

Probe format:  <magic><client-id>|<seq>            e.g. NESTPROBE1|pc01|42
               <magic><client-id>|<seq>|T<zeros>   (16 or more zeros) asks for the server's receive time:
                                                   the zeros are overwritten with microseconds since 1970 (UTC),
                                                   so the reply has exactly the request's length.

v2 (2026-11):
  * one-way loss: the server follows the sequence numbers of every client and counts probes that never
    arrived (= lost on the way TO the server), duplicates and late (out-of-order) probes.
    A client that sees more loss than the server reports lost the rest on the way BACK.
  * server receive time in the reply (opt-in, see above) -> split delay into "out" and "back".
  * per-minute summary per client: a log line and a CSV file <UDPECHO_STATSDIR>/udpecho-<yyyymmdd>.csv (UTC)
    columns: minute_utc,client_ip,client_id,received,missing,duplicate,late,restarts

Settings (environment variables):
  UDPECHO_PORT      UDP port to listen on                          (default 27015)
  UDPECHO_MAGIC     required prefix of every probe                  (default NESTPROBE1|)
  UDPECHO_MAXLEN    largest datagram that is answered               (default 512 bytes)
  UDPECHO_LOGSEC    log each client IP at most every N s            (default 600, 0 = no logging)
  UDPECHO_STATSDIR  folder for the per-minute CSV files             (default /data, empty = no CSV)
  UDPECHO_STATSLOG  1 = also print the per-minute summary lines     (default 1)
"""
import collections
import os
import socket
import time

PORT = int(os.environ.get("UDPECHO_PORT", "27015"))
MAGIC = os.environ.get("UDPECHO_MAGIC", "NESTPROBE1|").encode()
MAXLEN = int(os.environ.get("UDPECHO_MAXLEN", "512"))
LOGSEC = int(os.environ.get("UDPECHO_LOGSEC", "600"))
STATSDIR = os.environ.get("UDPECHO_STATSDIR", "/data")
STATSLOG = os.environ.get("UDPECHO_STATSLOG", "1") == "1"

MAX_STREAMS = 5000        # clients followed at the same time (protects memory)
MAX_ID = 64               # longest client id that is followed
SEEN = 4096               # recent sequence numbers kept per client (duplicate / late detection)
IDLE_SEC = 600            # forget a client after 10 min without probes
TS_MIN = 16               # minimum placeholder length for the server time


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Stream:
    """Sequence-number bookkeeping for one client (ip + id)."""
    __slots__ = ("hi", "seen", "order", "last", "recv", "missing", "dup", "late", "restarts")

    def __init__(self) -> None:
        self.hi = None
        self.seen: set[int] = set()
        self.order: collections.deque[int] = collections.deque()
        self.last = 0.0
        self.recv = self.missing = self.dup = self.late = self.restarts = 0

    def remember(self, s: int) -> None:
        self.seen.add(s)
        self.order.append(s)
        if len(self.order) > SEEN:
            self.seen.discard(self.order.popleft())

    def add(self, s: int, t: float) -> None:
        self.last = t
        if self.hi is None or s < self.hi - 100000 or (s <= 1 and self.hi > 10):
            if self.hi is not None:
                self.restarts += 1          # client restarted and counts from the beginning again
                self.seen.clear(); self.order.clear()
            self.hi = s; self.recv += 1; self.remember(s)
            return
        if s in self.seen:
            self.dup += 1                   # same probe twice (network duplicate)
            return
        self.recv += 1
        if s > self.hi:
            self.missing += s - self.hi - 1  # skipped numbers = not (yet) arrived
            self.hi = s
        else:
            self.late += 1                  # arrived after a higher number: it was counted missing before
            self.missing -= 1
        self.remember(s)

    def take(self) -> tuple[int, int, int, int, int]:
        r = (self.recv, self.missing, self.dup, self.late, self.restarts)
        self.recv = self.missing = self.dup = self.late = self.restarts = 0
        return r


def parse(data: bytes):
    """-> (client_id, seq, ts_offset or -1); None if the probe has no usable id|seq."""
    body = data[len(MAGIC):]
    ts = -1
    i = body.rfind(b"|T")
    if i >= 0 and len(body) - i - 2 >= TS_MIN and body[i + 2:].strip(b"0") == b"":
        ts = len(MAGIC) + i + 2
        body = body[:i]
    j = body.rfind(b"|")
    if j <= 0 or j > MAX_ID:
        return None, -1, ts
    try:
        seq = int(body[j + 1:])
    except ValueError:
        return None, -1, ts
    return body[:j].decode("ascii", "replace"), seq, ts


def flush(streams: dict, minute: int) -> None:
    """Write the finished minute for every client that sent something."""
    lines = []
    stamp = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(minute * 60))
    for (ip, cid), st in streams.items():
        recv, miss, dup, late, rst = st.take()
        if recv or miss or dup or late or rst:
            lines.append(f"{stamp},{ip},{cid},{recv},{miss},{dup},{late},{rst}")
            if STATSLOG:
                pct = 100.0 * max(miss, 0) / (recv + max(miss, 0)) if recv + max(miss, 0) else 0.0
                print(now_str(), f"minute {stamp} {ip} {cid}: received {recv}, missing {miss} ({pct:.2f} % lost on the way in), "
                      f"duplicate {dup}, late {late}" + (f", restarts {rst}" if rst else ""), flush=True)
    if lines and STATSDIR:
        path = os.path.join(STATSDIR, time.strftime("udpecho-%Y%m%d.csv", time.gmtime(minute * 60)))
        try:
            new = not os.path.exists(path)
            with open(path, "a", encoding="ascii") as f:
                if new:
                    f.write("minute_utc,client_ip,client_id,received,missing,duplicate,late,restarts\n")
                f.write("\n".join(lines) + "\n")
        except OSError as e:
            print(now_str(), f"cannot write {path}: {e}", flush=True)


def main() -> None:
    global STATSDIR
    if STATSDIR:
        try:
            os.makedirs(STATSDIR, exist_ok=True)
            test = os.path.join(STATSDIR, ".write-test")
            open(test, "w").close(); os.remove(test)
        except OSError as e:
            print(now_str(), f"per-minute CSV off: {STATSDIR} not writable ({e})", flush=True)
            STATSDIR = ""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    sock.settimeout(1.0)                    # wake up at least once a second to close finished minutes
    print(now_str(), f"UDPecho v2 listening on udp/{PORT}, prefix {MAGIC.decode()!r}, "
          f"per-minute CSV {'in ' + STATSDIR if STATSDIR else 'off'}", flush=True)
    last_log: dict[str, float] = {}
    count: dict[str, int] = {}
    streams: dict[tuple[str, str], Stream] = {}
    minute = int(time.time() // 60)
    while True:
        try:
            data, addr = sock.recvfrom(65535)   # full size: on Windows a too-small buffer raises instead of truncating
        except socket.timeout:
            data = None
        except OSError:                     # e.g. Windows "connection reset" after an ICMP port-unreachable: keep serving
            data = None
        t = time.time()
        if int(t // 60) != minute:
            flush(streams, minute)
            minute = int(t // 60)
            for k in [k for k, st in streams.items() if t - st.last > IDLE_SEC]:
                del streams[k]
        if data is None or len(data) > MAXLEN or not data.startswith(MAGIC):
            continue
        cid, seq, ts = parse(data)
        if ts >= 0:                         # opt-in server time: overwrite the zeros, same length
            n = len(data) - ts
            us = str(int(t * 1_000_000)).zfill(n)[-n:]
            data = data[:ts] + us.encode()
        try:
            sock.sendto(data, addr)
        except OSError:
            continue
        ip = addr[0]
        if cid is not None:
            key = (ip, cid)
            st = streams.get(key)
            if st is None and len(streams) < MAX_STREAMS:
                st = streams[key] = Stream()
            if st is not None:
                st.add(seq, t)
        if LOGSEC > 0:
            count[ip] = count.get(ip, 0) + 1
            if t - last_log.get(ip, 0) > LOGSEC:
                print(now_str(), "probes from", ip, "total", count[ip], flush=True)
                last_log[ip] = t


if __name__ == "__main__":
    main()
