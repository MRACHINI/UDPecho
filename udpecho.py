"""UDPecho - a tiny, safe UDP echo server for measuring packet loss and latency of game-like UDP traffic.

It answers ONLY datagrams that start with a magic prefix (default "NESTPROBE1|"), so it cannot be abused
to reflect or amplify traffic towards third parties: replies are never larger than the request and are
sent only to the sender of a correctly prefixed probe.

Settings (environment variables):
  UDPECHO_PORT    UDP port to listen on                 (default 27015)
  UDPECHO_MAGIC   required prefix of every probe         (default NESTPROBE1|)
  UDPECHO_MAXLEN  largest datagram that is answered      (default 512 bytes)
  UDPECHO_LOGSEC  log each client IP at most every N s   (default 600, 0 = no logging)
"""
import os
import socket
import time

PORT = int(os.environ.get("UDPECHO_PORT", "27015"))
MAGIC = os.environ.get("UDPECHO_MAGIC", "NESTPROBE1|").encode()
MAXLEN = int(os.environ.get("UDPECHO_MAXLEN", "512"))
LOGSEC = int(os.environ.get("UDPECHO_LOGSEC", "600"))


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    print(time.strftime("%Y-%m-%d %H:%M:%S"), f"UDPecho listening on udp/{PORT}, prefix {MAGIC.decode()!r}", flush=True)
    last_log: dict[str, float] = {}
    count: dict[str, int] = {}
    while True:
        data, addr = sock.recvfrom(MAXLEN + 1)
        if len(data) > MAXLEN or not data.startswith(MAGIC):
            continue
        sock.sendto(data, addr)
        if LOGSEC > 0:
            ip, now = addr[0], time.time()
            count[ip] = count.get(ip, 0) + 1
            if now - last_log.get(ip, 0) > LOGSEC:
                print(time.strftime("%Y-%m-%d %H:%M:%S"), "probes from", ip, "total", count[ip], flush=True)
                last_log[ip] = now


if __name__ == "__main__":
    main()
