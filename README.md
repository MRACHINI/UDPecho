# UDPecho

A tiny, safe **UDP echo server** for measuring packet loss and latency of game-like UDP traffic
between a site (e.g. a gaming café) and a server on the internet or at the ISP.

`ping` uses ICMP, which routers often treat differently from game traffic. UDPecho lets you send
real UDP datagrams (default port **27015**, the classic game-server port) and see exactly how many
come back and how fast.

## Safe by design

- Answers **only** datagrams that start with a magic prefix (default `NESTPROBE1|`) — random traffic
  is ignored, so the server cannot be used to reflect or amplify traffic at third parties.
- The reply is the request (never larger), sent only to the sender. The only change it ever makes is
  writing the server time into zeros the client reserved for it (see *Protocol*).
- Datagrams larger than 512 bytes are ignored.
- Runs as an unprivileged user; about 10 MB of RAM. 400 probes per second use a few % of one CPU core.

## Run it

**Docker (prebuilt image):**

```bash
docker run -d --name udpecho --restart unless-stopped -p 27015:27015/udp ghcr.io/mrachini/udpecho:latest
```

**Docker Compose:** `docker compose up -d` with the included `docker-compose.yml` (keeps the per-minute
CSV files in the `udpecho-data` volume).

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
| `UDPECHO_STATSDIR` | `/data`      | folder for the per-minute CSV files (empty = off) |
| `UDPECHO_STATSLOG` | `1`          | also print the per-minute summary lines (0 = off) |

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

**Which direction is slow?** Add `-ServerTime` (PowerShell) or `--server-time` (Python). Each reply then
carries the server's receive time and the client splits the round trip into **out** (to the server) and
**back**. The two clocks are not synchronised, so both are shown as *extra* delay compared with the fastest
probe — a slowdown that appears only in `out` happens on the way to the server, only in `back` on the way home:

```
reply 412  86 ms   out +27  back +1
...
45.63.98.97 udp/27015 : sent 600, lost 2 (0.3 %), rtt min/avg/max 57/71/131 ms, extra delay vs fastest: out avg 13.2 ms, back avg 0.8 ms
```

## Which direction is losing packets? (v2)

The server follows the sequence number of every client and counts probes that **never arrived** — those
were lost on the way **to** the server. Whatever else the client misses was lost on the way **back**:

```
lost on the way back = (client's lost) − (server's missing)
```

Once a minute the server writes one line per client to `<UDPECHO_STATSDIR>/udpecho-<yyyymmdd>.csv`
(UTC) and, with `UDPECHO_STATSLOG=1`, to the log (`docker logs udpecho`):

```
minute_utc,client_ip,client_id,received,missing,duplicate,late,restarts
2026-11-05T19:21Z,203.0.113.7,NGL012,598,2,0,0,0
```

| Column | Meaning |
|--------|---------|
| `received` | probes that arrived this minute |
| `missing` | sequence numbers skipped = lost on the way in (a late probe subtracts one again, so a minute can show −1) |
| `duplicate` | the same probe arrived twice |
| `late` | arrived after a higher number (re-ordered) |
| `restarts` | the client started counting from 1 again |

Up to 5000 clients are followed at a time; a client is forgotten after 10 minutes without probes.

## Protocol

Send any datagram starting with the magic prefix, e.g. `NESTPROBE1|pc01|42`; the server sends the same
bytes back. Put a sequence number after the prefix to match replies to requests:

| Request | Reply |
|---------|-------|
| `<magic><client-id>\|<seq>` | the same bytes |
| `<magic><client-id>\|<seq>\|T0000000000000000` (16+ zeros) | the zeros replaced by the server's receive time in microseconds since 1970 (UTC), same length |

The server only counts one-way loss for probes in this `<client-id>|<seq>` form (client id up to 64 characters).
Clients written for v1 keep working unchanged.
