# Analytics — ASE Traffic Control Plane

This document describes the analytics and observability provided by the Streamlit dashboard (`dashboard.py`) for the UDP packet processor, in line with practices used by engineering and traffic teams.

---

## Data sources

- **Shared memory** (`/dev/shm/telecom_shm`): Live counters and per-worker packet counts written by the C++ server. The dashboard reads this every 2 seconds.
- **Server log** (`server.log`): Stderr from the server. When the server is run with stderr redirected (e.g. `./server 2>&1 | tee server.log`), drop and validation messages include ISO8601 timestamps for time-based filtering.
- **Client log** (`client.log`): Client script output (e.g. send rate, invalid packet count).

---

## Counters (cumulative)

Cumulative values from shared memory since server start:

| Metric | Description |
|--------|-------------|
| **Total Packets Processed** | Number of packets that passed all validations and were processed. |
| **Dropped Packets** | Packets rejected due to validation failure (invalid magic, checksum, size, etc.). Delta vs previous value is shown when &gt; 0. |
| **Bytes Transferred** | Total bytes received in successfully processed packets (human-readable: B, KB, MB, GB). |
| **Uptime** | Time since the server started (from shared memory `start_time_sec`). |
| **Status** | **Running** or **Stopped** from the server heartbeat in shared memory. |

A warning is shown when dropped packets &gt; 0, suggesting to check the "Dropped & validation" log view.

---

## Throughput (rates)

Rates are computed from **deltas** between the current and previous snapshot (2-second refresh). They represent recent traffic, not long-term averages.

| Metric | Description |
|--------|-------------|
| **Packets/s** | Packets per second (delta of `packets_processed` over the interval). |
| **Bytes/s** | Bytes per second (delta of `bytes_transferred`). |
| **Drops/s** | Dropped packets per second (delta of `dropped_packets`). |
| **Drop rate %** | Percentage of packets that were dropped in that interval: `100 * delta_drops / delta_packets`. |

The first load after opening the dashboard may show zeros until the next refresh; after that, rates are stable for the chosen 2s interval.

---

## Worker throughput (per-thread)

Each of the four worker threads is shown with:

- **Throughput (p/s)**: Packets per second for that worker (from deltas of `thread_load[0..3]`).
- **Total packets**: Cumulative packets handled by that worker.
- **Bar**: Throughput relative to the **maximum** worker throughput (same scale across workers), not share of total. This highlights imbalance (e.g. one bar much shorter than others).

**Throughput distribution** is a second bar chart with the same scale (0 to max p/s), so you can see at a glance which workers are doing more work per second.

---

## Load balance

Load balance is summarized using the **coefficient of variation (CV)** of the four workers' throughputs:

- **CV = std(throughputs) / mean(throughputs)**. Lower means more even distribution.
- **Balanced** (green): CV &lt; 0.2.
- **Moderate skew** (orange): 0.2 ≤ CV &lt; 0.5.
- **Skewed** (red): CV ≥ 0.5.

This gives a single, interpretable indicator of how evenly load is spread across workers.

---

## Throughput over time (sparkline)

A sparkline shows **global packets/s** over the last ~60 samples (about 2 minutes at 2s refresh).

- **Y-axis**: Packets per second (global).
- **X-axis**: Time; oldest on the left, newest on the right.
- **Window**: Last N samples (e.g. "≈120s at 2s refresh").
- **Numeric summary** below the chart: **Current**, **Min**, and **Max** p/s in the window.

So you can see recent traffic level and spikes at a glance.

---

## Logs (detailed)

### Log filters (sidebar)

- **Time range**: **Last 1h**, **Last 6h**, **Last 24h**, **Last 48h**, or **All**. Only entries with a parsed timestamp in that window are shown; entries without a timestamp are always included.
- **Category**: **All logs** (tabs: Dropped & validation, Server log, Client log) or **Dropped & validation only** (only the drop/validation view).
- **Log lines**: Number of lines to show in the "Server log" and "Client log" tabs (10–500).

Log files are read from the **last 2 MB** so that 48h of logs can be covered when the server writes timestamped lines.

### Dropped & validation tab

This view shows only **server log lines** that correspond to dropped packets or validation failures. Each entry is rendered as a **card** with:

1. **Tag**: One of `MAGIC_WORD`, `CHECKSUM`, `TOO_SMALL`, `TOO_LARGE`, `SIZE_MISMATCH`, `LISTENER_ERROR`.
2. **Reason**: Short human-readable explanation (e.g. "Invalid magic word — packet sync marker did not match.").
3. **Details**: Key values parsed from the server message (e.g. received vs expected magic, expected vs calculated checksum, sizes).
4. **Raw log line**: Full server log line (with timestamp if present) in monospace.

So you see both the **reason**, the **numeric details**, and the **exact server message**.

### Drop/validation reason types

| Tag | Server condition | Typical reason text |
|-----|------------------|----------------------|
| **MAGIC_WORD** | Magic word ≠ 0xDEADBEEF | Invalid magic word — packet sync marker did not match. Details: Received (hex), Expected (hex). |
| **CHECKSUM** | Calculated checksum ≠ header checksum | Checksum mismatch — packet integrity check failed. Details: Expected checksum, Calculated checksum. |
| **TOO_SMALL** | Received bytes &lt; 12 (header size) | Packet too small — shorter than header size. Details: Received size, Minimum (header). |
| **TOO_LARGE** | Received bytes &gt; 4096 | Packet too large — exceeds buffer limit. Details: Received size, Maximum allowed. |
| **SIZE_MISMATCH** | Received bytes &lt; header + payload_len | Packet size mismatch — payload length in header does not match received bytes. Details: Expected (header + payload), Received. |
| **LISTENER_ERROR** | `recvfrom` failed | Listener recvfrom error — socket read failed. Details: Error message. |

The dashboard parses these messages with regex and fills the **Reason** and **Details** fields; the raw line is always shown for verification.

### Server log and Client log tabs

- **Server log**: Full server log (timestamped lines filtered by time range when applicable). Up to **Log lines** lines from the end of the filtered stream.
- **Client log**: Same idea for the client log. Lines without timestamps are included; when a time range is set, only lines with timestamps are filtered by time.

---

## Timestamps and time filtering

- **Server**: When the server is built with the timestamp change, each stderr line starts with `[YYYY-MM-DDTHH:MM:SS.mmmZ]`. The dashboard parses this and uses it for time-range filtering.
- **Client**: The client may not write ISO8601 timestamps; those lines have no parsed time and are always shown when the log is viewed.
- **Cutoff**: For "Last 1h/6h/24h/48h", the cutoff is `now - interval` in UTC. Any line with a parsed timestamp older than the cutoff is excluded from the Dropped & validation view and from the Server/Client log tabs.

---

## Refresh and performance

- The metrics and log views refresh **every 2 seconds** via a Streamlit fragment.
- Rate metrics and the sparkline use **session state** to keep the previous snapshot and a short history (e.g. 60 samples), so throughput and load balance are stable and the sparkline does not flicker unnecessarily.

For more on running the dashboard and the server, see the main [README](../README.md).
