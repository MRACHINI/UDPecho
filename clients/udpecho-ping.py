#!/usr/bin/env python3
"""'Ping' a UDPecho server over UDP (like ping, but with UDP datagrams like game traffic).

Usage: python3 udpecho-ping.py <server-ip> [-c COUNT] [-i INTERVAL_MS] [-p PORT]
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
a = ap.parse_args()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(a.timeout_ms / 1000)
dest = (socket.gethostbyname(a.target), a.port)
ident = f"{socket.gethostname()}-{os.getpid()}"
rtts, lost = [], 0
for i in range(1, a.count + 1):
    payload = f"{a.magic}{ident}|{i}".encode()
    t0 = time.perf_counter()
    sock.sendto(payload, dest)
    got = False
    while True:
        try:
            data, _ = sock.recvfrom(1024)
        except socket.timeout:
            break
        if data == payload:
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
print("\n" + summary)
