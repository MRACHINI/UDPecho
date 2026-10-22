# UDPecho

A tiny, safe **UDP echo server** for measuring packet loss and latency of game-like UDP traffic
between a site (e.g. a gaming café) and a server on the internet or at the ISP.

`ping` uses ICMP, which routers often treat differently from game traffic. UDPecho lets you send
real UDP datagrams (default port **27015**, the classic game-server port) and see exactly how many
come back and how fast.

## Safe by design

- Answers **only** datagrams that start with a magic prefix (default `NESTPROBE1|`) — random traffic
  is ignored, so the server cannot be used to reflect or amplify traffic at third parties.
- The reply is the unchanged request (never larger), sent only to the sender.
- Datagrams larger than 512 bytes are ignored.
- Runs as an unprivileged user; about 10 MB of RAM. 400 probes per second use a few % of one CPU core.

## Run it

**Docker (prebuilt image):**

```bash
docker run -d --name udpecho --restart unless-stopped -p 27015:27015/udp ghcr.io/mrachini/udpecho:latest
```

**Docker Compose:** `docker compose up -d` with the included `docker-compose.yml`.

**Without Docker (Python 3.8+):**

```bash
python3 udpecho.py
```

Make sure **UDP port 27015 inbound** is open in the firewall / cloud security group.

### Settings (environment variables)

| Variable         | Default        | Meaning                                       |
|------------------|----------------|-----------------------------------------------|
| `UDPECHO_PORT`   | `27015`        | UDP port to listen on                         |
| `UDPECHO_MAGIC`  | `NESTPROBE1\|` | required prefix of every probe                |
| `UDPECHO_MAXLEN` | `512`          | largest datagram that is answered             |
| `UDPECHO_LOGSEC` | `600`          | log each client IP at most every N seconds (0 = off) |

## Test it ("UDP ping")

**Windows (PowerShell):**

```powershell
.\clients\udpecho-ping.ps1 -Target <server-ip> -Count 600 -IntervalMs 100
```

**Linux / macOS:**

```bash
python3 clients/udpecho-ping.py <server-ip> -c 600 -i 100
```

Both print every reply, then a summary: probes sent, lost (%), and min/avg/max round-trip time.
600 probes at 100 ms = 1 minute.

## Protocol

Send any datagram starting with the magic prefix, e.g. `NESTPROBE1|pc01|42`; the server sends the same
bytes back. Put a sequence number after the prefix to match replies to requests.
