# "Ping" a UDPecho server over UDP - like ping.exe, but with UDP datagrams like game traffic.
# Usage:  .\udpecho-ping.ps1 -Target <server-ip> [-Count 600] [-IntervalMs 100] [-Port 27015]
param([Parameter(Mandatory)][string]$Target, [int]$Count = 100, [int]$IntervalMs = 100, [int]$Port = 27015, [int]$TimeoutMs = 1000, [string]$Magic = 'NESTPROBE1|')
$udp = New-Object System.Net.Sockets.UdpClient
$udp.Client.ReceiveTimeout = $TimeoutMs
$ep = New-Object System.Net.IPEndPoint([System.Net.Dns]::GetHostAddresses($Target)[0], $Port)
$rtts = New-Object System.Collections.Generic.List[double]; $lost = 0
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$id = "$env:COMPUTERNAME-$PID"
for ($i = 1; $i -le $Count; $i++) {
    $payload = "$Magic$id|$i"; $msg = [Text.Encoding]::ASCII.GetBytes($payload)
    $t0 = $sw.Elapsed.TotalMilliseconds
    [void]$udp.Send($msg, $msg.Length, $ep)
    $got = $false
    while (-not $got) {
        try {
            $from = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)
            if ([Text.Encoding]::ASCII.GetString($udp.Receive([ref]$from)) -eq $payload) { $got = $true; $ms = $sw.Elapsed.TotalMilliseconds - $t0; $rtts.Add($ms); "reply $i  {0:N0} ms" -f $ms }
        } catch { break }   # timeout
    }
    if (-not $got) { $lost++; "lost  $i" }
    $wait = $IntervalMs - ($sw.Elapsed.TotalMilliseconds - $t0); if ($wait -gt 0) { Start-Sleep -Milliseconds ([int]$wait) }
}
$udp.Close()
$s = $rtts | Measure-Object -Average -Minimum -Maximum
"`n$Target udp/$Port : sent $Count, lost $lost ({0:N1} %), rtt min/avg/max {1:N0}/{2:N0}/{3:N0} ms" -f (100 * $lost / $Count), $s.Minimum, $s.Average, $s.Maximum
