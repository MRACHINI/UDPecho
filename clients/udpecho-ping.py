#!/usr/bin/env python3
"""'Ping' a UDPecho server over UDP (like ping, but with UDP datagrams like game traffic).

Usage: python3 udpecho-ping.py <server-ip> [-c COUNT] [-i INTERVAL_MS] [-p PORT] [--server-time]

--server-time  (needs UDPECHO v2 on the server) asks for the server's receive time in every reply and
               splits each round trip into "out" (to the server) and "back". The two clocks are not in sync,
               so the split is shown as EXTRA delay compared with the fastest probe: if a slowdown shows up
               only in "out", it is on the way to the server; only in "back", on the way home.
"""
import argparse
import os
import socket
import statistics
import time

ap = argparse.ArgumentParser()
ap.add_argument("target")
ap.add_argument("-c", "--count", type=int, default=100)
ap.add_argument("-i", "--interval-ms", type=int, default=100)
ap.add_argument("-p", "--port", type=int, default=27015)
ap.add_argument("-t", "--timeout-ms", type=int, default=1000)
ap.add_argument("--magic", default="NESTPROBE1|")
ap.add_argument("--server-time", action="store_true", help="ask for the server receive time (UDPecho v2)")
a = ap.parse_args()

TS_LEN = 16
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(a.timeout_ms / 1000)
dest = (socket.gethostbyname(a.target), a.port)
ident = f"{socket.gethostname()}-{os.getpid()}"
rtts, lost, outs, backs = [], 0, [], []
best_out = best_back = None
for i in range(1, a.count + 1):
    head = f"{a.magic}{ident}|{i}"
    payload = (head + "|T" + "0" * TS_LEN if a.server_time else head).encode()
    t0 = time.perf_counter()
    w0 = time.time()
    sock.sendto(payload, dest)
    got = False
    while True:
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            break
        except ConnectionResetError:        # Windows: ICMP "port unreachable" (server not listening) = lost
            break
        if a.server_time and len(data) == len(payload) and data.startswith(head.encode() + b"|T"):
            ms = (time.perf_counter() - t0) * 1000
            srv = data[len(head) + 2:]
            if srv.strip(b"0") == b"":
                print("server does not fill in its time (UDPecho v1?) - run without --server-time")
                raise SystemExit(1)
            ts = int(srv) / 1e6
            out_raw = (ts - w0) * 1000                 # includes the unknown clock difference
            back_raw = ms - out_raw
            best_out = out_raw if best_out is None else min(best_out, out_raw)
            best_back = back_raw if best_back is None else min(best_back, back_raw)
            outs.append(out_raw); backs.append(back_raw); rtts.append(ms)
            print(f"reply {i}  {ms:.0f} ms   out +{out_raw - best_out:.0f}  back +{back_raw - best_back:.0f}")
            got = True
            break
        if not a.server_time and data == payload:
            ms = (time.perf_counter() - t0) * 1000
            rtts.append(ms)
            print(f"reply {i}  {ms:.0f} ms")
            got = True
            break
    if not got:
        lost += 1
        print(f"lost  {i}")
    wait = a.interval_ms / 1000 - (time.perf_counter() - t0)
    if wait > 0:
        time.sleep(wait)

summary = f"{a.target} udp/{a.port}: sent {a.count}, lost {lost} ({100 * lost / a.count:.1f} %)"
if rtts:
    summary += f", rtt min/avg/max {min(rtts):.0f}/{statistics.mean(rtts):.0f}/{max(rtts):.0f} ms"
if outs:
    summary += (f", extra delay vs fastest: out avg {statistics.mean(outs) - best_out:.1f} ms,"
                f" back avg {statistics.mean(backs) - best_back:.1f} ms")
print("\n" + summary)
